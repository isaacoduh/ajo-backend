import hashlib
import hmac
import json
import time
from collections.abc import AsyncIterator

import httpx
import pytest
from app.core.config import Settings
from app.db.session import get_session
from app.main import create_app
from app.modules.payments.models import PartnerEvent
from app.modules.payments.router import get_payment_rail_registry
from app.modules.payments.stripe_rail import (
    StripeRail,
    StripeWebhookVerificationError,
    map_payment_intent_state,
    verify_stripe_signature,
)
from app.modules.payments.types import (
    Capability,
    CollectionRequest,
    NotSupportedError,
    SettlementState,
    TopupRequest,
)
from fastapi import FastAPI
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

pytestmark = pytest.mark.stripe


def stripe_settings(**overrides: object) -> Settings:
    values = {
        "ENV": "test",
        "DATABASE_URL": "postgresql+asyncpg://ajo:ajo@localhost:5432/ajo",
        "REDIS_URL": "redis://localhost:6379/0",
        "JWT_ACCESS_SECRET": "local-only-access-secret-32-bytes",
        "REFRESH_TOKEN_PEPPER": "local-only-refresh-pepper-32-bytes",
        "STRIPE_SECRET_KEY": "sk_test_123",
        "STRIPE_WEBHOOK_SECRET": "whsec_test_123",
        "STRIPE_API_BASE_URL": "https://stripe.test",
    }
    values.update(overrides)
    return Settings(**values)


def signed_header(body: bytes, *, secret: str = "whsec_test_123", timestamp: int | None = None) -> str:
    event_timestamp = int(time.time()) if timestamp is None else timestamp
    signed_payload = f"{event_timestamp}.".encode() + body
    signature = hmac.new(secret.encode("utf-8"), signed_payload, hashlib.sha256).hexdigest()
    return f"t={event_timestamp},v1={signature}"


def payment_intent_payload(
    *,
    status: str = "requires_payment_method",
    idempotency_key: str = "stripe-topup-key",
) -> dict[str, object]:
    return {
        "id": "pi_test_123",
        "object": "payment_intent",
        "amount": 1250,
        "currency": "gbp",
        "status": status,
        "client_secret": "pi_test_123_secret_test",
        "livemode": False,
        "metadata": {
            "idempotency_key": idempotency_key,
            "ajo_flow": "topup",
            "user_id": "user-1",
        },
    }


def test_payment_intent_state_mapping() -> None:
    assert map_payment_intent_state("requires_payment_method") == SettlementState.INITIATED
    assert map_payment_intent_state("requires_action") == SettlementState.INITIATED
    assert map_payment_intent_state("processing") == SettlementState.PROCESSING
    assert map_payment_intent_state("succeeded") == SettlementState.SETTLED
    assert map_payment_intent_state("canceled") == SettlementState.FAILED
    assert map_payment_intent_state("unexpected") == SettlementState.PROCESSING


@pytest.mark.asyncio
async def test_stripe_topup_creates_payment_intent_with_idempotency_key() -> None:
    seen: dict[str, object] = {}

    def handler(request: httpx.Request) -> httpx.Response:
        seen["url"] = str(request.url)
        seen["authorization"] = request.headers["Authorization"]
        seen["idempotency_key"] = request.headers["Idempotency-Key"]
        seen["body"] = request.content.decode("utf-8")
        return httpx.Response(200, json=payment_intent_payload())

    async with httpx.AsyncClient(transport=httpx.MockTransport(handler)) as client:
        rail = StripeRail(settings=stripe_settings(), http_client=client)
        result = await rail.create_topup(
            TopupRequest(
                idempotency_key="stripe-topup-key",
                user_id="user-1",
                amount_minor=1250,
                currency="GBP",
            )
        )

    assert result.provider.value == "stripe"
    assert result.provider_object_id == "pi_test_123"
    assert result.state == SettlementState.INITIATED
    assert result.amount_minor == 1250
    assert result.currency == "GBP"
    assert result.provider_metadata == {
        "client_secret": "pi_test_123_secret_test",
        "status": "requires_payment_method",
        "livemode": False,
    }
    assert seen["url"] == "https://stripe.test/v1/payment_intents"
    assert seen["authorization"] == "Bearer sk_test_123"
    assert seen["idempotency_key"] == "stripe-topup-key"
    assert "amount=1250" in str(seen["body"])
    assert "automatic_payment_methods%5Ballow_redirects%5D=never" in str(seen["body"])
    assert "metadata%5Bajo_flow%5D=topup" in str(seen["body"])


@pytest.mark.asyncio
async def test_stripe_unsupported_capabilities_are_honest() -> None:
    rail = StripeRail(settings=stripe_settings())

    assert rail.supports(Capability.TOPUPS)
    assert not rail.supports(Capability.COLLECTIONS)

    with pytest.raises(NotSupportedError):
        await rail.collect(
            CollectionRequest(
                idempotency_key="collection-key",
                mandate_id="mandate-1",
                amount_minor=1000,
            )
        )


def test_stripe_webhook_signature_verification_accepts_matching_signature() -> None:
    body = b'{"id":"evt_test","data":{"object":{"id":"pi_test_123"}}}'

    verify_stripe_signature(
        body=body,
        signature_header=signed_header(body, timestamp=1_800_000_000),
        webhook_secret="whsec_test_123",
        now=1_800_000_001,
    )


def test_stripe_webhook_signature_verification_rejects_mismatch() -> None:
    body = b'{"id":"evt_test","data":{"object":{"id":"pi_test_123"}}}'

    with pytest.raises(StripeWebhookVerificationError):
        verify_stripe_signature(
            body=body,
            signature_header=signed_header(b"different-body", timestamp=1_800_000_000),
            webhook_secret="whsec_test_123",
            now=1_800_000_001,
        )


@pytest.mark.asyncio
async def test_stripe_webhook_round_trip_verifies_raw_payload() -> None:
    body = b'{"id":"evt_test","data":{"object":{"id":"pi_test_123"}}}'
    rail = StripeRail(settings=stripe_settings())

    result = await rail.verify_webhook(
        headers={"Stripe-Signature": signed_header(body)},
        body=body,
    )

    assert result.provider.value == "stripe"
    assert result.provider_event_id == "evt_test"
    assert result.provider_object_id == "pi_test_123"
    assert result.raw_payload == body


def webhook_app_for_session(
    db_session: AsyncSession,
    rail: StripeRail,
) -> FastAPI:
    app = create_app()

    async def override_session() -> AsyncIterator[AsyncSession]:
        yield db_session

    class Registry:
        def by_name(self, name: str) -> StripeRail:
            assert name == "stripe"
            return rail

    app.dependency_overrides[get_session] = override_session
    app.dependency_overrides[get_payment_rail_registry] = Registry
    return app


@pytest.mark.asyncio
async def test_stripe_webhook_route_persists_and_dedupes(
    test_env: None,
    db_session: AsyncSession,
) -> None:
    _ = test_env
    body = json.dumps(
        {
            "id": "evt_test",
            "type": "payment_intent.processing",
            "data": {"object": {"id": "pi_test_123"}},
        },
        separators=(",", ":"),
    ).encode("utf-8")

    def handler(request: httpx.Request) -> httpx.Response:
        assert str(request.url) == "https://stripe.test/v1/payment_intents/pi_test_123"
        return httpx.Response(
            200,
            json=payment_intent_payload(status="processing"),
        )

    async with httpx.AsyncClient(transport=httpx.MockTransport(handler)) as stripe_client:
        rail = StripeRail(settings=stripe_settings(), http_client=stripe_client)
        app = webhook_app_for_session(db_session, rail)
        transport = httpx.ASGITransport(app=app)
        async with httpx.AsyncClient(transport=transport, base_url="http://test") as client:
            first = await client.post(
                "/payments/webhooks/stripe",
                content=body,
                headers={"Stripe-Signature": signed_header(body)},
            )
            second = await client.post(
                "/payments/webhooks/stripe",
                content=body,
                headers={"Stripe-Signature": signed_header(body)},
            )

    assert first.status_code == 200, first.text
    assert first.json() == {"received": True, "deduped": False}
    assert second.status_code == 200
    assert second.json() == {"received": True, "deduped": True}

    events = (await db_session.execute(select(PartnerEvent))).scalars().all()
    assert len(events) == 1
    assert events[0].provider == "stripe"
    assert events[0].provider_event_id == "evt_test"
    assert events[0].provider_object_id == "pi_test_123"
