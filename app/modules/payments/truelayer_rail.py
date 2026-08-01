"""TrueLayer Payments v3 rail implementation."""

import base64
import json
from collections.abc import Callable, Mapping
from dataclasses import dataclass
from typing import Any
from urllib.parse import urljoin

import httpx
from pydantic import SecretStr
from truelayer_signing import (  # type: ignore[import-untyped]
    HttpMethod,
    TlSigningException,
    extract_jws_header,
    verify_with_jwks,
)

from app.core.config import Settings, get_settings
from app.modules.payments.truelayer_signing import (
    SignedTrueLayerRequest,
    build_signed_empty_request,
    build_signed_json_request,
)
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

TRUE_LAYER_PAYMENT_PATH = "/v3/payments"
TRUE_LAYER_PAYOUT_PATH = "/v3/payouts"
TRUE_LAYER_WEBHOOK_PATH = "/payments/webhooks/truelayer"
ALLOWED_WEBHOOK_JKUS = frozenset(
    {
        "https://webhooks.truelayer.com/.well-known/jwks",
        "https://webhooks.truelayer-sandbox.com/.well-known/jwks",
    }
)


class TrueLayerRailError(Exception):
    """Base exception for TrueLayer rail failures."""


class TrueLayerConfigurationError(TrueLayerRailError):
    """TrueLayer rail was called without required sandbox configuration."""


class TrueLayerWebhookVerificationError(TrueLayerRailError):
    """TrueLayer webhook signature or payload verification failed."""


@dataclass(frozen=True)
class TrueLayerApiResponse:
    id: str
    payload: dict[str, Any]


TrueLayerSigner = Callable[
    [
        str,
        str,
        HttpMethod,
        str,
        Mapping[str, Any],
        str,
        Mapping[str, str] | None,
    ],
    SignedTrueLayerRequest,
]


class TrueLayerRail:
    provider = ProviderName.TRUELAYER.value
    capabilities = frozenset({Capability.TOPUPS, Capability.PAYOUTS, Capability.WEBHOOKS})

    def __init__(
        self,
        settings: Settings | None = None,
        http_client: httpx.AsyncClient | None = None,
        signer: TrueLayerSigner | None = None,
    ) -> None:
        self.settings = settings if settings is not None else get_settings()
        self.http_client = http_client
        self.signer = signer if signer is not None else default_signer

    def supports(self, capability: Capability) -> bool:
        return capability in self.capabilities

    async def onboard_member(self, member: RailMember) -> RailOnboardingResult:
        _ = member
        raise NotSupportedError(Capability.ONBOARDING)

    async def create_topup(self, request: TopupRequest) -> RailOperationResult:
        access_token = await self._access_token()
        payload = self._payment_payload(request)
        signed = self.signer(
            self._key_id(),
            self._private_key_pem(),
            HttpMethod.POST,
            TRUE_LAYER_PAYMENT_PATH,
            payload,
            request.idempotency_key,
            {"Authorization": f"Bearer {access_token}"},
        )
        response = await self._post_signed(path=TRUE_LAYER_PAYMENT_PATH, signed=signed)
        return payment_result(
            response.payload,
            fallback_idempotency_key=request.idempotency_key,
            fallback_amount_minor=request.amount_minor,
            fallback_currency=request.currency,
        )

    async def create_mandate(self, request: MandateRequest) -> RailOperationResult:
        _ = request
        raise NotSupportedError(Capability.MANDATES)

    async def collect(self, request: CollectionRequest) -> RailOperationResult:
        _ = request
        raise NotSupportedError(Capability.COLLECTIONS)

    async def send_payout(self, request: PayoutRequest) -> RailOperationResult:
        if request.beneficiary_type != "business_account":
            raise NotSupportedError(Capability.PAYOUTS)
        access_token = await self._access_token()
        payload = self._business_account_payout_payload(request)
        signed = self.signer(
            self._key_id(),
            self._private_key_pem(),
            HttpMethod.POST,
            TRUE_LAYER_PAYOUT_PATH,
            payload,
            request.idempotency_key,
            {"Authorization": f"Bearer {access_token}"},
        )
        response = await self._post_signed(path=TRUE_LAYER_PAYOUT_PATH, signed=signed)
        return payout_result(
            response.payload,
            fallback_idempotency_key=request.idempotency_key,
            fallback_amount_minor=request.amount_minor,
            fallback_currency=request.currency,
        )

    async def get_settlement_status(self, provider_object_id: str) -> RailOperationResult:
        if looks_like_payout_id(provider_object_id):
            return await self._get_payout_status(provider_object_id)
        try:
            return await self._get_payment_status(provider_object_id)
        except TrueLayerRailError:
            return await self._get_payout_status(provider_object_id)

    async def _get_payment_status(self, provider_object_id: str) -> RailOperationResult:
        path = f"{TRUE_LAYER_PAYMENT_PATH}/{provider_object_id}"
        access_token = await self._access_token()
        signed = build_signed_empty_request(
            kid=self._key_id(),
            private_key_pem=self._private_key_pem(),
            method=HttpMethod.GET,
            path=path,
            idempotency_key=f"truelayer:get-payment:{provider_object_id}",
            extra_headers={"Authorization": f"Bearer {access_token}"},
        )
        response = await self._get_signed(path=path, signed=signed)
        return payment_result(response.payload, fallback_idempotency_key="")

    async def _get_payout_status(self, provider_object_id: str) -> RailOperationResult:
        path = f"{TRUE_LAYER_PAYOUT_PATH}/{provider_object_id}"
        access_token = await self._access_token()
        signed = build_signed_empty_request(
            kid=self._key_id(),
            private_key_pem=self._private_key_pem(),
            method=HttpMethod.GET,
            path=path,
            idempotency_key=f"truelayer:get-payout:{provider_object_id}",
            extra_headers={"Authorization": f"Bearer {access_token}"},
        )
        response = await self._get_signed(path=path, signed=signed)
        return payout_result(response.payload, fallback_idempotency_key="")

    async def verify_webhook(
        self,
        *,
        headers: dict[str, str],
        body: bytes,
    ) -> WebhookVerificationResult:
        signature_header = header_value(headers, "tl-signature")
        if signature_header is None:
            raise TrueLayerWebhookVerificationError("Missing Tl-Signature header.")
        try:
            jws_header = extract_jws_header(signature_header)
            if jws_header.jku not in ALLOWED_WEBHOOK_JKUS:
                raise TrueLayerWebhookVerificationError("Unexpected TrueLayer webhook JKU.")
            jwks = await self._fetch_jwks(jws_header.jku)
            verify_with_jwks(jwks, jws_header).set_method(HttpMethod.POST).set_path(
                TRUE_LAYER_WEBHOOK_PATH
            ).add_headers(headers).set_body(body.decode("utf-8")).verify(signature_header)
            payload = json.loads(body.decode("utf-8"))
            event_id = str(payload["event_id"])
            provider_object_id = webhook_provider_object_id(payload)
        except TrueLayerWebhookVerificationError:
            raise
        except (KeyError, TypeError, ValueError, json.JSONDecodeError, TlSigningException) as exc:
            raise TrueLayerWebhookVerificationError("Invalid TrueLayer webhook payload.") from exc
        return WebhookVerificationResult(
            provider=ProviderName.TRUELAYER,
            provider_event_id=event_id,
            provider_object_id=provider_object_id,
            raw_payload=body,
        )

    async def statement_lines(self) -> list[ProviderStatementLine]:
        raise NotSupportedError(Capability.RECONCILIATION)

    async def _access_token(self) -> str:
        response = await self._post_form(
            "/connect/token",
            data={
                "grant_type": "client_credentials",
                "client_id": self._client_id(),
                "client_secret": self._client_secret(),
                "scope": "payments",
            },
        )
        token = response.get("access_token")
        if not isinstance(token, str) or not token:
            raise TrueLayerRailError("TrueLayer auth response did not include an access token.")
        return token

    async def _post_form(self, path: str, *, data: dict[str, str]) -> dict[str, Any]:
        if self.http_client is not None:
            response = await self.http_client.post(self._auth_url(path), data=data)
        else:
            async with httpx.AsyncClient(timeout=15) as client:
                response = await client.post(self._auth_url(path), data=data)
        return parse_json_response(response, provider_name="TrueLayer auth")

    async def _post_signed(
        self,
        *,
        path: str,
        signed: SignedTrueLayerRequest,
    ) -> TrueLayerApiResponse:
        if self.http_client is not None:
            response = await self.http_client.post(
                self._api_url(path),
                content=signed.body,
                headers=signed.headers,
            )
        else:
            async with httpx.AsyncClient(timeout=15) as client:
                response = await client.post(
                    self._api_url(path),
                    content=signed.body,
                    headers=signed.headers,
                )
        payload = parse_json_response(response, provider_name="TrueLayer API")
        if not isinstance(payload.get("id"), str):
            raise TrueLayerRailError("TrueLayer response did not include an object id.")
        return TrueLayerApiResponse(id=payload["id"], payload=payload)

    async def _get_signed(
        self,
        *,
        path: str,
        signed: SignedTrueLayerRequest,
    ) -> TrueLayerApiResponse:
        if self.http_client is not None:
            response = await self.http_client.get(self._api_url(path), headers=signed.headers)
        else:
            async with httpx.AsyncClient(timeout=15) as client:
                response = await client.get(self._api_url(path), headers=signed.headers)
        payload = parse_json_response(response, provider_name="TrueLayer API")
        if not isinstance(payload.get("id"), str):
            raise TrueLayerRailError("TrueLayer response did not include an object id.")
        return TrueLayerApiResponse(id=payload["id"], payload=payload)

    async def _fetch_jwks(self, jku: str | None) -> dict[str, Any]:
        if jku is None:
            raise TrueLayerWebhookVerificationError("Missing TrueLayer webhook JKU.")
        if self.http_client is not None:
            response = await self.http_client.get(jku)
        else:
            async with httpx.AsyncClient(timeout=15) as client:
                response = await client.get(jku)
        return parse_json_response(response, provider_name="TrueLayer JWKS")

    def _payment_payload(self, request: TopupRequest) -> dict[str, Any]:
        return {
            "amount_in_minor": request.amount_minor,
            "currency": request.currency.upper(),
            "payment_method": {
                "type": "bank_transfer",
                "provider_selection": {
                    "type": "user_selected",
                    "scheme_selection": {
                        "type": "user_selected",
                        "allow_remitter_fee": False,
                    },
                },
                "beneficiary": {
                    "type": "merchant_account",
                    "merchant_account_id": self._merchant_account_id(),
                    "statement_reference": "AJO TOPUP",
                },
            },
            "hosted_page": {
                "country_code": "GB",
                "return_uri": self._redirect_uri(),
                "language_code": "en",
            },
            "user": {
                "id": request.user_id,
                "name": "Ajo Member",
                "email": f"member-{request.user_id}@ajo.local",
            },
            "metadata": {
                "ajo_flow": "topup",
                "idempotency_key": request.idempotency_key,
                "user_id": request.user_id,
            },
        }

    def _business_account_payout_payload(self, request: PayoutRequest) -> dict[str, Any]:
        return {
            "merchant_account_id": self._merchant_account_id(),
            "amount_in_minor": request.amount_minor,
            "currency": request.currency.upper(),
            "beneficiary": {
                "type": "business_account",
                "reference": "AJO PAYOUT",
            },
            "metadata": {
                "ajo_flow": "payout",
                "idempotency_key": request.idempotency_key,
                "user_id": request.user_id,
                "payout_type": "business_account",
            },
        }

    def _api_url(self, path: str) -> str:
        base_url = self.settings.truelayer_api_base_url.rstrip("/") + "/"
        return urljoin(base_url, path.lstrip("/"))

    def _auth_url(self, path: str) -> str:
        base_url = self.settings.truelayer_auth_base_url.rstrip("/") + "/"
        return urljoin(base_url, path.lstrip("/"))

    def _client_id(self) -> str:
        if self.settings.truelayer_client_id is None:
            raise TrueLayerConfigurationError("TRUELAYER_CLIENT_ID is required for TrueLayerRail.")
        return self.settings.truelayer_client_id

    def _client_secret(self) -> str:
        return required_secret(
            self.settings.truelayer_client_secret,
            "TRUELAYER_CLIENT_SECRET is required for TrueLayerRail.",
        )

    def _key_id(self) -> str:
        if self.settings.truelayer_key_id is None:
            raise TrueLayerConfigurationError("TRUELAYER_KEY_ID is required for TrueLayerRail.")
        return self.settings.truelayer_key_id

    def _private_key_pem(self) -> str:
        encoded = required_secret(
            self.settings.truelayer_private_key_pem_b64,
            "TRUELAYER_PRIVATE_KEY_PEM_B64 is required for TrueLayerRail.",
        )
        try:
            return base64.b64decode(encoded).decode("utf-8")
        except ValueError as exc:
            raise TrueLayerConfigurationError("TRUELAYER_PRIVATE_KEY_PEM_B64 is invalid.") from exc

    def _merchant_account_id(self) -> str:
        if self.settings.truelayer_merchant_account_id is None:
            raise TrueLayerConfigurationError(
                "TRUELAYER_MERCHANT_ACCOUNT_ID is required for TrueLayerRail."
            )
        return self.settings.truelayer_merchant_account_id

    def _redirect_uri(self) -> str:
        if self.settings.truelayer_redirect_uri is None:
            raise TrueLayerConfigurationError(
                "TRUELAYER_REDIRECT_URI is required for TrueLayerRail."
            )
        return self.settings.truelayer_redirect_uri


def default_signer(
    kid: str,
    private_key_pem: str,
    method: HttpMethod,
    path: str,
    payload: Mapping[str, Any],
    idempotency_key: str,
    extra_headers: Mapping[str, str] | None,
) -> SignedTrueLayerRequest:
    return build_signed_json_request(
        kid=kid,
        private_key_pem=private_key_pem,
        method=method,
        path=path,
        payload=payload,
        idempotency_key=idempotency_key,
        extra_headers=extra_headers,
    )


def parse_json_response(response: httpx.Response, *, provider_name: str) -> dict[str, Any]:
    try:
        payload = response.json()
    except json.JSONDecodeError as exc:
        raise TrueLayerRailError(f"{provider_name} returned a non-JSON response.") from exc
    if response.status_code >= 400:
        message = f"{provider_name} request failed."
        if isinstance(payload, dict):
            error = payload.get("error")
            if isinstance(error, str):
                message = error
            elif isinstance(error, dict) and isinstance(error.get("message"), str):
                message = error["message"]
        raise TrueLayerRailError(message)
    if not isinstance(payload, dict):
        raise TrueLayerRailError(f"{provider_name} returned an invalid JSON response.")
    return payload


def payment_result(
    payload: dict[str, Any],
    *,
    fallback_idempotency_key: str,
    fallback_amount_minor: int | None = None,
    fallback_currency: str = "GBP",
) -> RailOperationResult:
    metadata = payload.get("metadata")
    metadata_dict = metadata if isinstance(metadata, dict) else {}
    amount_minor = (
        int(payload["amount_in_minor"])
        if payload.get("amount_in_minor") is not None
        else fallback_amount_minor
    )
    return RailOperationResult(
        provider=ProviderName.TRUELAYER,
        provider_object_id=str(payload["id"]),
        idempotency_key=str(metadata_dict.get("idempotency_key") or fallback_idempotency_key),
        state=map_payment_state(str(payload.get("status", ""))),
        amount_minor=amount_minor,
        currency=str(payload.get("currency", fallback_currency)).upper(),
        provider_metadata=payment_metadata(payload),
    )


def payment_metadata(payload: dict[str, Any]) -> dict[str, Any]:
    metadata: dict[str, Any] = {"truelayer_object_type": "payment"}
    for key in ("status", "resource_token", "created_at"):
        if key in payload:
            metadata[key] = payload[key]
    hosted_page = payload.get("hosted_page")
    if isinstance(hosted_page, dict) and isinstance(hosted_page.get("uri"), str):
        metadata["hosted_page_uri"] = hosted_page["uri"]
    return metadata


def payout_result(
    payload: dict[str, Any],
    *,
    fallback_idempotency_key: str,
    fallback_amount_minor: int | None = None,
    fallback_currency: str = "GBP",
) -> RailOperationResult:
    metadata = payload.get("metadata")
    metadata_dict = metadata if isinstance(metadata, dict) else {}
    amount_minor = (
        int(payload["amount_in_minor"])
        if payload.get("amount_in_minor") is not None
        else fallback_amount_minor
    )
    return RailOperationResult(
        provider=ProviderName.TRUELAYER,
        provider_object_id=str(payload["id"]),
        idempotency_key=str(metadata_dict.get("idempotency_key") or fallback_idempotency_key),
        state=map_payout_state(str(payload.get("status", ""))),
        amount_minor=amount_minor,
        currency=str(payload.get("currency", fallback_currency)).upper(),
        provider_metadata=payout_metadata(payload),
    )


def payout_metadata(payload: dict[str, Any]) -> dict[str, Any]:
    metadata: dict[str, Any] = {"truelayer_object_type": "payout"}
    for key in ("status", "created_at", "executed_at", "failed_at", "failure_reason", "scheme_id"):
        if key in payload:
            metadata[key] = payload[key]
    beneficiary = payload.get("beneficiary")
    if isinstance(beneficiary, dict):
        beneficiary_type = beneficiary.get("type")
        if isinstance(beneficiary_type, str):
            metadata["beneficiary_type"] = beneficiary_type
        reference = beneficiary.get("reference")
        if isinstance(reference, str):
            metadata["beneficiary_reference"] = reference
    return metadata


def map_payment_state(status: str) -> SettlementState:
    if status in {"authorization_required", "authorizing"}:
        return SettlementState.INITIATED
    if status in {"authorized", "executed"}:
        return SettlementState.PROCESSING
    if status in {"settled", "payment_creditable"}:
        return SettlementState.SETTLED
    if status in {"failed", "rejected", "revoked", "expired", "cancelled", "canceled"}:
        return SettlementState.FAILED
    return SettlementState.PROCESSING


def map_payout_state(status: str) -> SettlementState:
    if status in {"pending", "authorized", "authorizing", "submitted", "processing"}:
        return SettlementState.PROCESSING
    if status == "executed":
        return SettlementState.SETTLED
    if status in {"failed", "rejected", "cancelled", "canceled"}:
        return SettlementState.FAILED
    return SettlementState.PROCESSING


def looks_like_payout_id(provider_object_id: str) -> bool:
    return provider_object_id.startswith(("payout_", "pout_"))


def webhook_provider_object_id(payload: dict[str, Any]) -> str:
    event_type = str(payload["type"])
    if event_type.startswith("payout_") or "payout_id" in payload:
        return str(payload["payout_id"])
    return str(payload["payment_id"])


def header_value(headers: dict[str, str], name: str) -> str | None:
    for header_name, value in headers.items():
        if header_name.lower() == name.lower():
            return value
    return None


def required_secret(value: SecretStr | None, message: str) -> str:
    if value is None:
        raise TrueLayerConfigurationError(message)
    return value.get_secret_value()
