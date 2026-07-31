"""Payment rail shared types."""

from dataclasses import dataclass
from enum import StrEnum
from typing import Any


class Capability(StrEnum):
    ONBOARDING = "onboarding"
    TOPUPS = "topups"
    MANDATES = "mandates"
    COLLECTIONS = "collections"
    PAYOUTS = "payouts"
    WEBHOOKS = "webhooks"
    RECONCILIATION = "reconciliation"


class SettlementState(StrEnum):
    INITIATED = "initiated"
    PROCESSING = "processing"
    SETTLED = "settled"
    FAILED = "failed"
    FAILED_LATE = "failed_late"


class PaymentFlow(StrEnum):
    TOPUP = "topup"
    COLLECTION = "collection"
    PAYOUT = "payout"


class ProviderName(StrEnum):
    FAKE = "fake"
    STRIPE = "stripe"
    TRUELAYER = "truelayer"


@dataclass(frozen=True)
class RailMember:
    user_id: str
    email: str


@dataclass(frozen=True)
class RailOnboardingResult:
    provider: ProviderName
    provider_member_id: str


@dataclass(frozen=True)
class TopupRequest:
    idempotency_key: str
    user_id: str
    amount_minor: int
    currency: str = "GBP"


@dataclass(frozen=True)
class MandateRequest:
    idempotency_key: str
    user_id: str


@dataclass(frozen=True)
class CollectionRequest:
    idempotency_key: str
    mandate_id: str
    amount_minor: int
    currency: str = "GBP"


@dataclass(frozen=True)
class PayoutRequest:
    idempotency_key: str
    user_id: str
    amount_minor: int
    currency: str = "GBP"


@dataclass(frozen=True)
class RailOperationResult:
    provider: ProviderName
    provider_object_id: str
    idempotency_key: str
    state: SettlementState
    amount_minor: int | None = None
    currency: str = "GBP"
    provider_metadata: dict[str, Any] | None = None


@dataclass(frozen=True)
class WebhookVerificationResult:
    provider: ProviderName
    provider_event_id: str
    provider_object_id: str
    raw_payload: bytes


@dataclass(frozen=True)
class ProviderStatementLine:
    provider: ProviderName
    provider_object_id: str
    idempotency_key: str
    amount_minor: int
    currency: str
    state: SettlementState


class NotSupportedError(Exception):
    def __init__(self, capability: Capability) -> None:
        self.capability = capability
        super().__init__(f"Capability not supported: {capability.value}")
