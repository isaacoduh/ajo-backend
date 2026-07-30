"""Stripe payment rail implementation."""

import hashlib
import hmac
import json
import time
from dataclasses import dataclass
from typing import Any
from urllib.parse import urljoin

import httpx

from app.core.config import Settings, get_settings
from app.modules.payments.types import (
    Capability,
    CollectionRequest,
    MandateRequest,
    NotSupportedError,
    PayoutRequest,
    ProviderName,
    ProviderStatementLine,
    RailMember,
    RailOnboardingResult,
    RailOperationResult,
    SettlementState,
    TopupRequest,
    WebhookVerificationResult,
)


class StripeRailError(Exception):
    """Base exception for Stripe rail failures."""


class StripeConfigurationError(StripeRailError):
    """Stripe rail was called without required sandbox configuration."""


class StripeWebhookVerificationError(StripeRailError):
    """Stripe webhook signature or payload verification failed."""


@dataclass(frozen=True)
class StripeApiResponse:
    id: str
    payload: dict[str, Any]


class StripeRail:
    provider = ProviderName.STRIPE.value
    capabilities = frozenset(
        {
            Capability.ONBOARDING,
            Capability.TOPUPS,
            Capability.WEBHOOKS,
            Capability.RECONCILIATION,
        }
    )

    def __init__(
        self,
        settings: Settings | None = None,
        http_client: httpx.AsyncClient | None = None,
    ) -> None:
        self.settings = settings if settings is not None else get_settings()
        self.http_client = http_client

    def supports(self, capability: Capability) -> bool:
        return capability in self.capabilities

    async def onboard_member(self, member: RailMember) -> RailOnboardingResult:
        if not self.supports(Capability.ONBOARDING):
            raise NotSupportedError(Capability.ONBOARDING)
        if not self.settings.stripe_connect_enabled:
            raise NotSupportedError(Capability.ONBOARDING)

        account = await self._post(
            "/v1/accounts",
            data={
                "type": "express",
                "country": "GB",
                "email": member.email,
                "capabilities[transfers][requested]": "true",
                "business_type": "individual",
                "metadata[user_id]": member.user_id,
            },
            idempotency_key=f"stripe:onboard:{member.user_id}:account",
        )
        await self._post(
            "/v1/account_links",
            data={
                "account": account.id,
                "type": "account_onboarding",
                "refresh_url": self._required_connect_url("refresh"),
                "return_url": self._required_connect_url("return"),
            },
            idempotency_key=f"stripe:onboard:{member.user_id}:account_link",
        )
        return RailOnboardingResult(
            provider=ProviderName.STRIPE,
            provider_member_id=account.id,
        )

    async def create_topup(self, request: TopupRequest) -> RailOperationResult:
        response = await self._post(
            "/v1/payment_intents",
            data={
                "amount": str(request.amount_minor),
                "currency": request.currency.lower(),
                "automatic_payment_methods[enabled]": "true",
                "automatic_payment_methods[allow_redirects]": "never",
                "metadata[user_id]": request.user_id,
                "metadata[idempotency_key]": request.idempotency_key,
                "metadata[ajo_flow]": "topup",
            },
            idempotency_key=request.idempotency_key,
        )
        return payment_intent_result(response.payload, fallback_idempotency_key=request.idempotency_key)

    async def create_mandate(self, request: MandateRequest) -> RailOperationResult:
        _ = request
        raise NotSupportedError(Capability.MANDATES)

    async def collect(self, request: CollectionRequest) -> RailOperationResult:
        _ = request
        raise NotSupportedError(Capability.COLLECTIONS)

    async def send_payout(self, request: PayoutRequest) -> RailOperationResult:
        _ = request
        raise NotSupportedError(Capability.PAYOUTS)

    async def get_settlement_status(self, provider_object_id: str) -> RailOperationResult:
        response = await self._get(f"/v1/payment_intents/{provider_object_id}")
        return payment_intent_result(response.payload, fallback_idempotency_key="")

    async def verify_webhook(
        self,
        *,
        headers: dict[str, str],
        body: bytes,
    ) -> WebhookVerificationResult:
        webhook_secret = self._webhook_secret()
        signature_header = header_value(headers, "stripe-signature")
        if signature_header is None:
            raise StripeWebhookVerificationError("Missing Stripe-Signature header.")
        verify_stripe_signature(
            body=body,
            signature_header=signature_header,
            webhook_secret=webhook_secret,
        )
        try:
            payload = json.loads(body.decode("utf-8"))
            event_id = str(payload["id"])
            provider_object_id = str(payload["data"]["object"]["id"])
        except (KeyError, TypeError, ValueError, json.JSONDecodeError) as exc:
            raise StripeWebhookVerificationError("Invalid Stripe webhook payload.") from exc
        return WebhookVerificationResult(
            provider=ProviderName.STRIPE,
            provider_event_id=event_id,
            provider_object_id=provider_object_id,
            raw_payload=body,
        )

    async def statement_lines(self) -> list[ProviderStatementLine]:
        response = await self._get(
            "/v1/payment_intents",
            params={"limit": "100"},
        )
        lines: list[ProviderStatementLine] = []
        for item in response.payload.get("data", []):
            if not isinstance(item, dict):
                continue
            result = payment_intent_result(item, fallback_idempotency_key="")
            lines.append(
                ProviderStatementLine(
                    provider=result.provider,
                    provider_object_id=result.provider_object_id,
                    idempotency_key=result.idempotency_key,
                    amount_minor=result.amount_minor or 0,
                    currency=result.currency,
                    state=result.state,
                )
            )
        return lines

    async def _post(
        self,
        path: str,
        *,
        data: dict[str, str],
        idempotency_key: str,
    ) -> StripeApiResponse:
        headers = {
            "Authorization": f"Bearer {self._secret_key()}",
            "Idempotency-Key": idempotency_key,
        }
        if self.http_client is not None:
            response = await self.http_client.post(self._url(path), data=data, headers=headers)
        else:
            async with httpx.AsyncClient(timeout=15) as client:
                response = await client.post(self._url(path), data=data, headers=headers)
        return parse_stripe_response(response)

    async def _get(
        self,
        path: str,
        *,
        params: dict[str, str] | None = None,
    ) -> StripeApiResponse:
        headers = {"Authorization": f"Bearer {self._secret_key()}"}
        if self.http_client is not None:
            response = await self.http_client.get(self._url(path), params=params, headers=headers)
        else:
            async with httpx.AsyncClient(timeout=15) as client:
                response = await client.get(self._url(path), params=params, headers=headers)
        return parse_stripe_response(response)

    def _url(self, path: str) -> str:
        base_url = self.settings.stripe_api_base_url.rstrip("/") + "/"
        return urljoin(base_url, path.lstrip("/"))

    def _secret_key(self) -> str:
        if self.settings.stripe_secret_key is None:
            raise StripeConfigurationError("STRIPE_SECRET_KEY is required for StripeRail.")
        return self.settings.stripe_secret_key.get_secret_value()

    def _webhook_secret(self) -> str:
        if self.settings.stripe_webhook_secret is None:
            raise StripeConfigurationError("STRIPE_WEBHOOK_SECRET is required for Stripe webhooks.")
        return self.settings.stripe_webhook_secret.get_secret_value()

    def _required_connect_url(self, kind: str) -> str:
        if kind == "refresh" and self.settings.stripe_connect_refresh_url is not None:
            return self.settings.stripe_connect_refresh_url
        if kind == "return" and self.settings.stripe_connect_return_url is not None:
            return self.settings.stripe_connect_return_url
        raise StripeConfigurationError("Stripe Connect onboarding URLs are required.")


def parse_stripe_response(response: httpx.Response) -> StripeApiResponse:
    try:
        payload = response.json()
    except json.JSONDecodeError as exc:
        raise StripeRailError("Stripe returned a non-JSON response.") from exc
    if response.status_code >= 400:
        message = "Stripe API request failed."
        if isinstance(payload, dict):
            error = payload.get("error")
            if isinstance(error, dict) and isinstance(error.get("message"), str):
                message = error["message"]
        raise StripeRailError(message)
    if not isinstance(payload, dict) or not isinstance(payload.get("id"), str):
        raise StripeRailError("Stripe response did not include an object id.")
    return StripeApiResponse(id=payload["id"], payload=payload)


def payment_intent_result(
    payload: dict[str, Any],
    *,
    fallback_idempotency_key: str,
) -> RailOperationResult:
    provider_object_id = str(payload["id"])
    metadata = payload.get("metadata")
    metadata_dict = metadata if isinstance(metadata, dict) else {}
    idempotency_key = str(metadata_dict.get("idempotency_key") or fallback_idempotency_key)
    return RailOperationResult(
        provider=ProviderName.STRIPE,
        provider_object_id=provider_object_id,
        idempotency_key=idempotency_key,
        state=map_payment_intent_state(str(payload.get("status", ""))),
        amount_minor=int(payload["amount"]) if payload.get("amount") is not None else None,
        currency=str(payload.get("currency", "gbp")).upper(),
        provider_metadata=payment_intent_metadata(payload),
    )


def payment_intent_metadata(payload: dict[str, Any]) -> dict[str, Any]:
    keys = {
        "client_secret",
        "payment_method_types",
        "status",
        "latest_charge",
        "created",
        "livemode",
    }
    return {key: payload[key] for key in keys if key in payload}


def map_payment_intent_state(status: str) -> SettlementState:
    if status in {"requires_payment_method", "requires_confirmation", "requires_action"}:
        return SettlementState.INITIATED
    if status in {"processing", "requires_capture"}:
        return SettlementState.PROCESSING
    if status == "succeeded":
        return SettlementState.SETTLED
    if status == "canceled":
        return SettlementState.FAILED
    return SettlementState.PROCESSING


def header_value(headers: dict[str, str], name: str) -> str | None:
    for header_name, value in headers.items():
        if header_name.lower() == name.lower():
            return value
    return None


def verify_stripe_signature(
    *,
    body: bytes,
    signature_header: str,
    webhook_secret: str,
    tolerance_seconds: int = 300,
    now: int | None = None,
) -> None:
    timestamp, signatures = parse_signature_header(signature_header)
    current_time = int(time.time()) if now is None else now
    if abs(current_time - timestamp) > tolerance_seconds:
        raise StripeWebhookVerificationError("Stripe webhook timestamp is outside tolerance.")
    signed_payload = f"{timestamp}.".encode() + body
    expected = hmac.new(
        webhook_secret.encode("utf-8"),
        signed_payload,
        hashlib.sha256,
    ).hexdigest()
    if not any(hmac.compare_digest(expected, signature) for signature in signatures):
        raise StripeWebhookVerificationError("Stripe webhook signature mismatch.")


def parse_signature_header(signature_header: str) -> tuple[int, list[str]]:
    timestamp: int | None = None
    signatures: list[str] = []
    for part in signature_header.split(","):
        key, _, value = part.partition("=")
        if key == "t":
            try:
                timestamp = int(value)
            except ValueError as exc:
                raise StripeWebhookVerificationError("Invalid Stripe webhook timestamp.") from exc
        elif key == "v1":
            signatures.append(value)
    if timestamp is None or not signatures:
        raise StripeWebhookVerificationError("Invalid Stripe-Signature header.")
    return timestamp, signatures
