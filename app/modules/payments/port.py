"""Payment rail port."""

from typing import Protocol

from app.modules.payments.types import (
    Capability,
    CollectionRequest,
    MandateRequest,
    PayoutRequest,
    ProviderStatementLine,
    RailMember,
    RailOnboardingResult,
    RailOperationResult,
    TopupRequest,
    WebhookVerificationResult,
)


class PaymentRailPort(Protocol):
    provider: str
    capabilities: frozenset[Capability]

    def supports(self, capability: Capability) -> bool: ...

    async def onboard_member(self, member: RailMember) -> RailOnboardingResult: ...

    async def create_topup(self, request: TopupRequest) -> RailOperationResult: ...

    async def create_mandate(self, request: MandateRequest) -> RailOperationResult: ...

    async def collect(self, request: CollectionRequest) -> RailOperationResult: ...

    async def send_payout(self, request: PayoutRequest) -> RailOperationResult: ...

    async def get_settlement_status(self, provider_object_id: str) -> RailOperationResult: ...

    async def verify_webhook(
        self,
        *,
        headers: dict[str, str],
        body: bytes,
    ) -> WebhookVerificationResult: ...

    async def statement_lines(self) -> list[ProviderStatementLine]: ...

