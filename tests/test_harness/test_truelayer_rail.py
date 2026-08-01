import base64
import json
from collections.abc import AsyncIterator, Mapping
from typing import Any
from uuid import UUID

import httpx
import pytest
from app.core.config import Settings
from app.db.ledger import PostingInput, PostingSide
from app.db.session import get_session
from app.main import create_app
from app.modules.identity.models import User
from app.modules.ledger.service import LedgerService
from app.modules.members.models import Member
from app.modules.payments.models import PartnerEvent
from app.modules.payments.registry import PaymentRailRegistry, default_registry
from app.modules.payments.repo import PaymentsRepo
from app.modules.payments.router import get_payment_rail_registry
from app.modules.payments.service import PaymentsService
from app.modules.payments.truelayer_rail import (
    TRUE_LAYER_PAYMENT_PATH,
    TRUE_LAYER_PAYOUT_PATH,
    TRUE_LAYER_WEBHOOK_PATH,
    TrueLayerRail,
    map_payment_state,
    map_payout_state,
)
from app.modules.payments.truelayer_signing import SignedTrueLayerRequest
from app.modules.payments.types import (
    Capability,
    NotSupportedError,
    PaymentFlow,
    PayoutRequest,
    ProviderName,
    RailOperationResult,
    SettlementState,
    TopupRequest,
)
from app.modules.wallets.repo import WalletsRepo
from app.modules.wallets.service import PLATFORM_SETTLEMENT_ACCOUNT_CODE, WalletService
from cryptography.hazmat.primitives import serialization
from cryptography.hazmat.primitives.asymmetric import ec
from fastapi import FastAPI
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession
from truelayer_signing import HttpMethod, sign_with_pem  # type: ignore[import-untyped]

pytestmark = pytest.mark.truelayer
SANDBOX_WEBHOOK_JKU = "https://webhooks.truelayer-sandbox.com/.well-known/jwks"


def truelayer_settings(**overrides: object) -> Settings:
    values = {
        "ENV": "test",
        "DATABASE_URL": "postgresql+asyncpg://ajo:ajo@localhost:5432/ajo",
        "REDIS_URL": "redis://localhost:6379/0",
        "JWT_ACCESS_SECRET": "local-only-access-secret-32-bytes",
        "REFRESH_TOKEN_PEPPER": "local-only-refresh-pepper-32-bytes",
        "TRUELAYER_CLIENT_ID": "tl-client-id",
        "TRUELAYER_CLIENT_SECRET": "tl-client-secret",
        "TRUELAYER_KEY_ID": "tl-key-id",
        "TRUELAYER_PRIVATE_KEY_PEM_B64": base64.b64encode(b"private-key").decode("ascii"),
        "TRUELAYER_MERCHANT_ACCOUNT_ID": "ma_test_123",
        "TRUELAYER_REDIRECT_URI": "https://app.test/wallet/topups/return",
        "TRUELAYER_API_BASE_URL": "https://api.truelayer.test",
        "TRUELAYER_AUTH_BASE_URL": "https://auth.truelayer.test",
    }
    values.update(overrides)
    return Settings(**values)


def generated_private_key_pem() -> str:
    private_key = ec.generate_private_key(ec.SECP521R1())
    return private_key.private_bytes(
        encoding=serialization.Encoding.PEM,
        format=serialization.PrivateFormat.TraditionalOpenSSL,
        encryption_algorithm=serialization.NoEncryption(),
    ).decode("utf-8")


def public_jwks_from_private_pem(
    *, kid: str, private_key_pem: str
) -> dict[str, list[dict[str, str]]]:
    private_key = serialization.load_pem_private_key(private_key_pem.encode("utf-8"), password=None)
    if not isinstance(private_key, ec.EllipticCurvePrivateKey):
        raise TypeError("Expected EC private key.")
    public_numbers = private_key.public_key().public_numbers()
    return {
        "keys": [
            {
                "kty": "EC",
                "kid": kid,
                "crv": "P-521",
                "x": base64url_uint(public_numbers.x),
                "y": base64url_uint(public_numbers.y),
            }
        ]
    }


def base64url_uint(value: int) -> str:
    return base64.urlsafe_b64encode(value.to_bytes(66, "big")).decode("ascii").rstrip("=")


def signed_truelayer_webhook_header(*, body: bytes, private_key_pem: str) -> str:
    return (
        sign_with_pem("tl-key-id", private_key_pem)
        .set_method(HttpMethod.POST)
        .set_path(TRUE_LAYER_WEBHOOK_PATH)
        .add_header("X-TL-Webhook-Timestamp", "2026-08-01T12:00:00Z")
        .set_body(body.decode("utf-8"))
        .set_jku(SANDBOX_WEBHOOK_JKU)
        .sign()
    )


async def create_member_user(db_session: AsyncSession, *, email: str) -> tuple[User, Member]:
    user = User(email=email, password_hash="hash")
    db_session.add(user)
    await db_session.flush()
    member = Member(
        user_id=user.id,
        display_name=email,
        country="GB",
        screening_state="clear",
    )
    db_session.add(member)
    await db_session.flush()
    return user, member


async def seed_available_balance(
    wallet_service: WalletService,
    *,
    member_id: UUID,
    amount_minor: int,
) -> None:
    wallet = await wallet_service.ensure_for_member(member_id=member_id)
    platform = await wallet_service.ledger_service.get_account_by_code(
        PLATFORM_SETTLEMENT_ACCOUNT_CODE
    )
    available = await wallet_service.ledger_service.get_account_by_code(
        wallet.available_account_code
    )
    assert platform is not None
    assert available is not None
    await wallet_service.ledger_service.post_entry(
        idempotency_key=f"truelayer-seed-available-{member_id}-{amount_minor}",
        description="Seed available wallet balance",
        postings=[
            PostingInput(
                account_id=platform.id,
                side=PostingSide.DEBIT,
                amount_minor=amount_minor,
            ),
            PostingInput(
                account_id=available.id,
                side=PostingSide.CREDIT,
                amount_minor=amount_minor,
            ),
        ],
    )


def webhook_app_for_session(
    db_session: AsyncSession,
    rail: TrueLayerRail,
) -> FastAPI:
    app = create_app()

    async def override_session() -> AsyncIterator[AsyncSession]:
        yield db_session

    class Registry:
        def by_name(self, name: str) -> TrueLayerRail:
            assert name == "truelayer"
            return rail

    app.dependency_overrides[get_session] = override_session
    app.dependency_overrides[get_payment_rail_registry] = Registry
    return app


class TrueLayerLikeTopupRail:
    provider = "truelayer"

    async def create_topup(self, request: TopupRequest) -> RailOperationResult:
        return RailOperationResult(
            provider=ProviderName.TRUELAYER,
            provider_object_id="pay_test_123",
            idempotency_key=request.idempotency_key,
            state=SettlementState.INITIATED,
            amount_minor=request.amount_minor,
            currency=request.currency,
            provider_metadata={"hosted_page_uri": "https://payment.truelayer.test/hosted/pay"},
        )


class TrueLayerLikePayoutRail:
    provider = "truelayer"

    def __init__(
        self,
        provider_object_id: str = "796cab79-cd1a-4e01-8241-93ac28bf4260",
    ) -> None:
        self.provider_object_id = provider_object_id

    async def send_payout(self, request: PayoutRequest) -> RailOperationResult:
        return RailOperationResult(
            provider=ProviderName.TRUELAYER,
            provider_object_id=self.provider_object_id,
            idempotency_key=request.idempotency_key,
            state=SettlementState.PROCESSING,
            amount_minor=request.amount_minor,
            currency=request.currency,
            provider_metadata={"truelayer_object_type": "payout"},
        )


def fake_signer(
    kid: str,
    private_key_pem: str,
    method: HttpMethod,
    path: str,
    payload: Mapping[str, Any],
    idempotency_key: str,
    extra_headers: Mapping[str, str] | None,
) -> SignedTrueLayerRequest:
    assert kid == "tl-key-id"
    assert private_key_pem == "private-key"
    assert method == HttpMethod.POST
    assert path in {TRUE_LAYER_PAYMENT_PATH, TRUE_LAYER_PAYOUT_PATH}
    body = json.dumps(payload, separators=(",", ":"), sort_keys=False).encode()
    return SignedTrueLayerRequest(
        body=body,
        headers={
            "Content-Type": "application/json",
            "Idempotency-Key": idempotency_key,
            "Tl-Signature": "tl-signature-test",
            **dict(extra_headers or {}),
        },
    )


@pytest.mark.asyncio
async def test_truelayer_topup_creates_hosted_payment_with_signed_body() -> None:
    seen: dict[str, Any] = {}

    async def handler(request: httpx.Request) -> httpx.Response:
        if str(request.url) == "https://auth.truelayer.test/connect/token":
            form = dict(item.split("=") for item in request.content.decode().split("&"))
            assert form["grant_type"] == "client_credentials"
            assert form["client_id"] == "tl-client-id"
            assert form["client_secret"] == "tl-client-secret"
            assert form["scope"] == "payments"
            return httpx.Response(200, json={"access_token": "tl-access-token"})

        seen["url"] = str(request.url)
        seen["headers"] = dict(request.headers)
        seen["body"] = json.loads(request.content)
        return httpx.Response(
            201,
            json={
                "id": "pay_test_123",
                "amount_in_minor": 380000,
                "currency": "GBP",
                "status": "authorization_required",
                "hosted_page": {"uri": "https://payment.truelayer.test/hosted/pay_test_123"},
                "metadata": {
                    "idempotency_key": "tl-topup-1",
                    "ajo_flow": "topup",
                    "user_id": "user-1",
                },
            },
        )

    async with httpx.AsyncClient(transport=httpx.MockTransport(handler)) as client:
        rail = TrueLayerRail(
            settings=truelayer_settings(),
            http_client=client,
            signer=fake_signer,
        )
        result = await rail.create_topup(
            TopupRequest(
                idempotency_key="tl-topup-1",
                user_id="user-1",
                amount_minor=380000,
                currency="GBP",
            )
        )

    assert result.provider.value == "truelayer"
    assert result.provider_object_id == "pay_test_123"
    assert result.idempotency_key == "tl-topup-1"
    assert result.state == SettlementState.INITIATED
    assert result.provider_metadata == {
        "truelayer_object_type": "payment",
        "status": "authorization_required",
        "hosted_page_uri": "https://payment.truelayer.test/hosted/pay_test_123",
    }
    assert seen["url"] == "https://api.truelayer.test/v3/payments"
    assert seen["headers"]["authorization"] == "Bearer tl-access-token"
    assert seen["headers"]["idempotency-key"] == "tl-topup-1"
    assert seen["headers"]["tl-signature"] == "tl-signature-test"
    assert seen["body"]["amount_in_minor"] == 380000
    assert seen["body"]["payment_method"]["beneficiary"] == {
        "type": "merchant_account",
        "merchant_account_id": "ma_test_123",
        "statement_reference": "AJO TOPUP",
    }
    assert seen["body"]["hosted_page"] == {
        "country_code": "GB",
        "return_uri": "https://app.test/wallet/topups/return",
        "language_code": "en",
    }


@pytest.mark.asyncio
async def test_truelayer_topup_uses_request_amount_when_create_response_omits_amount() -> None:
    async def handler(request: httpx.Request) -> httpx.Response:
        if str(request.url) == "https://auth.truelayer.test/connect/token":
            return httpx.Response(200, json={"access_token": "tl-access-token"})
        return httpx.Response(
            201,
            json={
                "id": "pay_test_without_amount",
                "status": "authorization_required",
                "hosted_page": {"uri": "https://payment.truelayer.test/hosted/pay_without_amount"},
                "metadata": {
                    "idempotency_key": "tl-topup-without-amount",
                    "ajo_flow": "topup",
                    "user_id": "user-1",
                },
            },
        )

    async with httpx.AsyncClient(transport=httpx.MockTransport(handler)) as client:
        rail = TrueLayerRail(
            settings=truelayer_settings(),
            http_client=client,
            signer=fake_signer,
        )
        result = await rail.create_topup(
            TopupRequest(
                idempotency_key="tl-topup-without-amount",
                user_id="user-1",
                amount_minor=3000,
                currency="GBP",
            )
        )

    assert result.amount_minor == 3000
    assert result.currency == "GBP"
    assert result.state == SettlementState.INITIATED


@pytest.mark.asyncio
async def test_truelayer_payout_creates_business_account_payout_with_signed_body() -> None:
    seen: dict[str, Any] = {}

    async def handler(request: httpx.Request) -> httpx.Response:
        if str(request.url) == "https://auth.truelayer.test/connect/token":
            return httpx.Response(200, json={"access_token": "tl-access-token"})

        seen["url"] = str(request.url)
        seen["headers"] = dict(request.headers)
        seen["body"] = json.loads(request.content)
        return httpx.Response(
            201,
            json={
                "id": "796cab79-cd1a-4e01-8241-93ac28bf4260",
                "amount_in_minor": 2400,
                "currency": "GBP",
                "status": "pending",
                "beneficiary": {"type": "business_account", "reference": "AJO PAYOUT"},
                "metadata": {
                    "idempotency_key": "tl-payout-1",
                    "ajo_flow": "payout",
                    "user_id": "user-1",
                    "payout_type": "business_account",
                },
            },
        )

    async with httpx.AsyncClient(transport=httpx.MockTransport(handler)) as client:
        rail = TrueLayerRail(
            settings=truelayer_settings(),
            http_client=client,
            signer=fake_signer,
        )
        result = await rail.send_payout(
            PayoutRequest(
                idempotency_key="tl-payout-1",
                user_id="user-1",
                amount_minor=2400,
                currency="GBP",
            )
        )

    assert result.provider.value == "truelayer"
    assert result.provider_object_id == "796cab79-cd1a-4e01-8241-93ac28bf4260"
    assert result.idempotency_key == "tl-payout-1"
    assert result.state == SettlementState.PROCESSING
    assert result.provider_metadata == {
        "truelayer_object_type": "payout",
        "status": "pending",
        "beneficiary_type": "business_account",
        "beneficiary_reference": "AJO PAYOUT",
    }
    assert seen["url"] == "https://api.truelayer.test/v3/payouts"
    assert seen["headers"]["authorization"] == "Bearer tl-access-token"
    assert seen["headers"]["idempotency-key"] == "tl-payout-1"
    assert seen["headers"]["tl-signature"] == "tl-signature-test"
    assert seen["body"] == {
        "merchant_account_id": "ma_test_123",
        "amount_in_minor": 2400,
        "currency": "GBP",
        "beneficiary": {
            "type": "business_account",
            "reference": "AJO PAYOUT",
        },
        "metadata": {
            "ajo_flow": "payout",
            "idempotency_key": "tl-payout-1",
            "user_id": "user-1",
            "payout_type": "business_account",
        },
    }


@pytest.mark.asyncio
async def test_truelayer_rejects_unsupported_payout_beneficiary_type() -> None:
    rail = TrueLayerRail(settings=truelayer_settings())

    with pytest.raises(NotSupportedError):
        await rail.send_payout(
            PayoutRequest(
                idempotency_key="tl-payout-external",
                user_id="user-1",
                amount_minor=2400,
                beneficiary_type="external_account",
            )
        )


def test_truelayer_maps_payment_states() -> None:
    assert map_payment_state("authorization_required") == SettlementState.INITIATED
    assert map_payment_state("executed") == SettlementState.PROCESSING
    assert map_payment_state("payment_creditable") == SettlementState.SETTLED
    assert map_payment_state("failed") == SettlementState.FAILED
    assert map_payment_state("unknown") == SettlementState.PROCESSING


def test_truelayer_maps_payout_states() -> None:
    assert map_payout_state("pending") == SettlementState.PROCESSING
    assert map_payout_state("authorized") == SettlementState.PROCESSING
    assert map_payout_state("executed") == SettlementState.SETTLED
    assert map_payout_state("failed") == SettlementState.FAILED
    assert map_payout_state("unknown") == SettlementState.PROCESSING


def test_registry_selects_truelayer_for_topups() -> None:
    rail = default_registry().for_flow(
        PaymentFlow.TOPUP,
        settings=truelayer_settings(RAIL_TOPUP="truelayer"),
    )

    assert isinstance(rail, TrueLayerRail)


@pytest.mark.asyncio
async def test_truelayer_unsupported_capabilities_are_honest() -> None:
    rail = TrueLayerRail(settings=truelayer_settings())

    assert rail.supports(Capability.TOPUPS)
    assert rail.supports(Capability.PAYOUTS)
    assert rail.supports(Capability.WEBHOOKS)
    assert not rail.supports(Capability.RECONCILIATION)
    with pytest.raises(NotSupportedError):
        await rail.statement_lines()


@pytest.mark.asyncio
async def test_truelayer_webhook_route_persists_dedupes_and_settles_topup(
    test_env: None,
    db_session: AsyncSession,
) -> None:
    _ = test_env
    private_key_pem = generated_private_key_pem()
    jwks = public_jwks_from_private_pem(kid="tl-key-id", private_key_pem=private_key_pem)
    body = json.dumps(
        {
            "type": "payment_creditable",
            "event_version": 1,
            "event_id": "evt_tl_test",
            "payment_id": "pay_test_123",
            "metadata": {
                "idempotency_key": "truelayer-topup-key",
                "ajo_flow": "topup",
                "user_id": "user-1",
            },
        },
        separators=(",", ":"),
    ).encode("utf-8")
    signature = signed_truelayer_webhook_header(body=body, private_key_pem=private_key_pem)
    user, member = await create_member_user(db_session, email="truelayer-settle@example.com")
    wallet_service = WalletService(
        WalletsRepo(db_session),
        LedgerService(db_session),
        PaymentsService(PaymentsRepo(db_session)),
        PaymentRailRegistry(
            {
                "fake": TrueLayerLikeTopupRail(),
                "truelayer": TrueLayerLikeTopupRail(),
            }
        ),  # type: ignore[dict-item]
    )
    await wallet_service.create_topup(
        member_id=member.id,
        user_id=user.id,
        amount_minor=1250,
        currency="GBP",
        idempotency_key="truelayer-topup-key",
    )

    async def handler(request: httpx.Request) -> httpx.Response:
        if str(request.url) == SANDBOX_WEBHOOK_JKU:
            return httpx.Response(200, json=jwks)
        if str(request.url) == "https://auth.truelayer.test/connect/token":
            return httpx.Response(200, json={"access_token": "tl-access-token"})
        assert str(request.url) == "https://api.truelayer.test/v3/payments/pay_test_123"
        assert request.headers["Authorization"] == "Bearer tl-access-token"
        assert request.headers["Idempotency-Key"] == "truelayer:get-payment:pay_test_123"
        return httpx.Response(
            200,
            json={
                "id": "pay_test_123",
                "amount_in_minor": 1250,
                "currency": "GBP",
                "status": "payment_creditable",
                "metadata": {
                    "idempotency_key": "truelayer-topup-key",
                    "ajo_flow": "topup",
                    "user_id": "user-1",
                },
            },
        )

    settings = truelayer_settings(
        TRUELAYER_PRIVATE_KEY_PEM_B64=base64.b64encode(private_key_pem.encode("utf-8")).decode(
            "ascii"
        )
    )
    async with httpx.AsyncClient(transport=httpx.MockTransport(handler)) as truelayer_client:
        rail = TrueLayerRail(settings=settings, http_client=truelayer_client)
        app = webhook_app_for_session(db_session, rail)
        transport = httpx.ASGITransport(app=app)
        async with httpx.AsyncClient(transport=transport, base_url="http://test") as client:
            first = await client.post(
                "/payments/webhooks/truelayer",
                content=body,
                headers={
                    "Tl-Signature": signature,
                    "X-TL-Webhook-Timestamp": "2026-08-01T12:00:00Z",
                },
            )
            second = await client.post(
                "/payments/webhooks/truelayer",
                content=body,
                headers={
                    "Tl-Signature": signature,
                    "X-TL-Webhook-Timestamp": "2026-08-01T12:00:00Z",
                },
            )

    assert first.status_code == 200, first.text
    assert first.json() == {"received": True, "deduped": False}
    assert second.status_code == 200
    assert second.json() == {"received": True, "deduped": True}

    events = (await db_session.execute(select(PartnerEvent))).scalars().all()
    assert len(events) == 1
    assert events[0].provider == "truelayer"
    assert events[0].provider_event_id == "evt_tl_test"
    assert events[0].provider_object_id == "pay_test_123"

    balance = await wallet_service.balance_for_member(member_id=member.id)
    assert balance.pending_minor == 0
    assert balance.available_minor == 1250


@pytest.mark.asyncio
async def test_truelayer_payout_executed_webhook_settles_wallet_withdrawal(
    test_env: None,
    db_session: AsyncSession,
) -> None:
    _ = test_env
    private_key_pem = generated_private_key_pem()
    jwks = public_jwks_from_private_pem(kid="tl-key-id", private_key_pem=private_key_pem)
    payout_id = "796cab79-cd1a-4e01-8241-93ac28bf4260"
    body = json.dumps(
        {
            "type": "payout_executed",
            "event_version": 1,
            "event_id": "evt_tl_payout_executed",
            "payout_id": payout_id,
            "executed_at": "2026-08-01T12:00:00Z",
            "beneficiary": {"type": "business_account"},
        },
        separators=(",", ":"),
    ).encode("utf-8")
    signature = signed_truelayer_webhook_header(body=body, private_key_pem=private_key_pem)
    user, member = await create_member_user(db_session, email="truelayer-payout@example.com")
    wallet_service = WalletService(
        WalletsRepo(db_session),
        LedgerService(db_session),
        PaymentsService(PaymentsRepo(db_session)),
        PaymentRailRegistry(
            {
                "fake": TrueLayerLikePayoutRail(provider_object_id=payout_id),
                "truelayer": TrueLayerLikePayoutRail(provider_object_id=payout_id),
            }
        ),  # type: ignore[dict-item]
    )
    await seed_available_balance(wallet_service, member_id=member.id, amount_minor=5000)
    await wallet_service.create_withdrawal(
        member_id=member.id,
        user_id=user.id,
        amount_minor=1500,
        currency="GBP",
        idempotency_key="truelayer-wallet-payout-key",
    )

    async def handler(request: httpx.Request) -> httpx.Response:
        if str(request.url) == SANDBOX_WEBHOOK_JKU:
            return httpx.Response(200, json=jwks)
        if str(request.url) == "https://auth.truelayer.test/connect/token":
            return httpx.Response(200, json={"access_token": "tl-access-token"})
        if str(request.url) == f"https://api.truelayer.test/v3/payments/{payout_id}":
            return httpx.Response(404, json={"error": "not_found"})
        assert str(request.url) == f"https://api.truelayer.test/v3/payouts/{payout_id}"
        assert request.headers["Authorization"] == "Bearer tl-access-token"
        assert request.headers["Idempotency-Key"] == f"truelayer:get-payout:{payout_id}"
        return httpx.Response(
            200,
            json={
                "id": payout_id,
                "merchant_account_id": "ma_test_123",
                "amount_in_minor": 1500,
                "currency": "GBP",
                "status": "executed",
                "beneficiary": {"type": "business_account", "reference": "AJO PAYOUT"},
                "metadata": {
                    "idempotency_key": "truelayer-wallet-payout-key",
                    "ajo_flow": "payout",
                    "user_id": str(user.id),
                },
            },
        )

    settings = truelayer_settings(
        TRUELAYER_PRIVATE_KEY_PEM_B64=base64.b64encode(private_key_pem.encode("utf-8")).decode(
            "ascii"
        )
    )
    async with httpx.AsyncClient(transport=httpx.MockTransport(handler)) as truelayer_client:
        rail = TrueLayerRail(settings=settings, http_client=truelayer_client)
        app = webhook_app_for_session(db_session, rail)
        transport = httpx.ASGITransport(app=app)
        async with httpx.AsyncClient(transport=transport, base_url="http://test") as client:
            first = await client.post(
                "/payments/webhooks/truelayer",
                content=body,
                headers={
                    "Tl-Signature": signature,
                    "X-TL-Webhook-Timestamp": "2026-08-01T12:00:00Z",
                },
            )
            second = await client.post(
                "/payments/webhooks/truelayer",
                content=body,
                headers={
                    "Tl-Signature": signature,
                    "X-TL-Webhook-Timestamp": "2026-08-01T12:00:00Z",
                },
            )

    assert first.status_code == 200, first.text
    assert first.json() == {"received": True, "deduped": False}
    assert second.status_code == 200
    assert second.json() == {"received": True, "deduped": True}

    events = (await db_session.execute(select(PartnerEvent))).scalars().all()
    assert len(events) == 1
    assert events[0].provider_object_id == payout_id

    balance = await wallet_service.balance_for_member(member_id=member.id)
    assert balance.pending_minor == 0
    assert balance.available_minor == 3500


@pytest.mark.asyncio
async def test_truelayer_payout_failed_webhook_releases_wallet_withdrawal(
    test_env: None,
    db_session: AsyncSession,
) -> None:
    _ = test_env
    private_key_pem = generated_private_key_pem()
    jwks = public_jwks_from_private_pem(kid="tl-key-id", private_key_pem=private_key_pem)
    payout_id = "0a495e9f-2f41-4669-ba33-85407c0b26cb"
    body = json.dumps(
        {
            "type": "payout_failed",
            "event_version": 1,
            "event_id": "evt_tl_payout_failed",
            "payout_id": payout_id,
            "failed_at": "2026-08-01T12:00:00Z",
            "failure_reason": "insufficient_funds",
            "beneficiary": {"type": "business_account"},
        },
        separators=(",", ":"),
    ).encode("utf-8")
    signature = signed_truelayer_webhook_header(body=body, private_key_pem=private_key_pem)
    user, member = await create_member_user(db_session, email="truelayer-payout-failed@example.com")
    wallet_service = WalletService(
        WalletsRepo(db_session),
        LedgerService(db_session),
        PaymentsService(PaymentsRepo(db_session)),
        PaymentRailRegistry(
            {
                "fake": TrueLayerLikePayoutRail(provider_object_id=payout_id),
                "truelayer": TrueLayerLikePayoutRail(provider_object_id=payout_id),
            }
        ),  # type: ignore[dict-item]
    )
    await seed_available_balance(wallet_service, member_id=member.id, amount_minor=5000)
    await wallet_service.create_withdrawal(
        member_id=member.id,
        user_id=user.id,
        amount_minor=1500,
        currency="GBP",
        idempotency_key="truelayer-wallet-payout-failed-key",
    )

    async def handler(request: httpx.Request) -> httpx.Response:
        if str(request.url) == SANDBOX_WEBHOOK_JKU:
            return httpx.Response(200, json=jwks)
        if str(request.url) == "https://auth.truelayer.test/connect/token":
            return httpx.Response(200, json={"access_token": "tl-access-token"})
        if str(request.url) == f"https://api.truelayer.test/v3/payments/{payout_id}":
            return httpx.Response(404, json={"error": "not_found"})
        assert str(request.url) == f"https://api.truelayer.test/v3/payouts/{payout_id}"
        return httpx.Response(
            200,
            json={
                "id": payout_id,
                "merchant_account_id": "ma_test_123",
                "amount_in_minor": 1500,
                "currency": "GBP",
                "status": "failed",
                "failure_reason": "insufficient_funds",
                "beneficiary": {"type": "business_account", "reference": "AJO PAYOUT"},
                "metadata": {
                    "idempotency_key": "truelayer-wallet-payout-failed-key",
                    "ajo_flow": "payout",
                    "user_id": str(user.id),
                },
            },
        )

    settings = truelayer_settings(
        TRUELAYER_PRIVATE_KEY_PEM_B64=base64.b64encode(private_key_pem.encode("utf-8")).decode(
            "ascii"
        )
    )
    async with httpx.AsyncClient(transport=httpx.MockTransport(handler)) as truelayer_client:
        rail = TrueLayerRail(settings=settings, http_client=truelayer_client)
        app = webhook_app_for_session(db_session, rail)
        transport = httpx.ASGITransport(app=app)
        async with httpx.AsyncClient(transport=transport, base_url="http://test") as client:
            response = await client.post(
                "/payments/webhooks/truelayer",
                content=body,
                headers={
                    "Tl-Signature": signature,
                    "X-TL-Webhook-Timestamp": "2026-08-01T12:00:00Z",
                },
            )

    assert response.status_code == 200, response.text
    assert response.json() == {"received": True, "deduped": False}

    balance = await wallet_service.balance_for_member(member_id=member.id)
    assert balance.pending_minor == 0
    assert balance.available_minor == 5000
