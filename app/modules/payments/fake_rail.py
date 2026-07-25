"""Fake payment rail for tests and local demos."""

import json
from dataclasses import dataclass

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


@dataclass
class FakeRailObject:
    result: RailOperationResult
    event_counter: int = 0


class FakeRail:
    provider = ProviderName.FAKE.value
    capabilities = frozenset(
        {
            Capability.ONBOARDING,
            Capability.TOPUPS,
            Capability.MANDATES,
            Capability.COLLECTIONS,
            Capability.PAYOUTS,
            Capability.WEBHOOKS,
            Capability.RECONCILIATION,
        }
    )

    def __init__(self) -> None:
        self._objects_by_id: dict[str, FakeRailObject] = {}
        self._objects_by_idempotency_key: dict[str, str] = {}
        self._member_counter = 0
        self._object_counter = 0

    def supports(self, capability: Capability) -> bool:
        return capability in self.capabilities

    async def onboard_member(self, member: RailMember) -> RailOnboardingResult:
        if not self.supports(Capability.ONBOARDING):
            raise NotSupportedError(Capability.ONBOARDING)
        self._member_counter += 1
        return RailOnboardingResult(
            provider=ProviderName.FAKE,
            provider_member_id=f"fake_member_{self._member_counter}_{member.user_id}",
        )

    async def create_topup(self, request: TopupRequest) -> RailOperationResult:
        return self._create_or_reuse(
            idempotency_key=request.idempotency_key,
            prefix="topup",
            amount_minor=request.amount_minor,
            currency=request.currency,
        )

    async def create_mandate(self, request: MandateRequest) -> RailOperationResult:
        return self._create_or_reuse(
            idempotency_key=request.idempotency_key,
            prefix="mandate",
            amount_minor=None,
            currency="GBP",
        )

    async def collect(self, request: CollectionRequest) -> RailOperationResult:
        _ = request.mandate_id
        return self._create_or_reuse(
            idempotency_key=request.idempotency_key,
            prefix="collection",
            amount_minor=request.amount_minor,
            currency=request.currency,
        )

    async def send_payout(self, request: PayoutRequest) -> RailOperationResult:
        return self._create_or_reuse(
            idempotency_key=request.idempotency_key,
            prefix="payout",
            amount_minor=request.amount_minor,
            currency=request.currency,
        )

    async def get_settlement_status(self, provider_object_id: str) -> RailOperationResult:
        return self._objects_by_id[provider_object_id].result

    async def verify_webhook(
        self,
        *,
        headers: dict[str, str],
        body: bytes,
    ) -> WebhookVerificationResult:
        _ = headers
        payload = json.loads(body.decode())
        return WebhookVerificationResult(
            provider=ProviderName.FAKE,
            provider_event_id=str(payload["event_id"]),
            provider_object_id=str(payload["object_id"]),
            raw_payload=body,
        )

    async def statement_lines(self) -> list[ProviderStatementLine]:
        return [
            ProviderStatementLine(
                provider=result.provider,
                provider_object_id=result.provider_object_id,
                idempotency_key=result.idempotency_key,
                amount_minor=result.amount_minor or 0,
                currency=result.currency,
                state=result.state,
            )
            for result in (stored.result for stored in self._objects_by_id.values())
        ]

    def advance(self, provider_object_id: str, state: SettlementState) -> RailOperationResult:
        stored = self._objects_by_id[provider_object_id]
        if not valid_transition(stored.result.state, state):
            raise ValueError(f"Invalid transition {stored.result.state.value} -> {state.value}")
        stored.result = RailOperationResult(
            provider=stored.result.provider,
            provider_object_id=stored.result.provider_object_id,
            idempotency_key=stored.result.idempotency_key,
            state=state,
            amount_minor=stored.result.amount_minor,
            currency=stored.result.currency,
        )
        return stored.result

    def settle(self, provider_object_id: str) -> RailOperationResult:
        current = self._objects_by_id[provider_object_id].result.state
        if current == SettlementState.INITIATED:
            self.advance(provider_object_id, SettlementState.PROCESSING)
        return self.advance(provider_object_id, SettlementState.SETTLED)

    def fail(self, provider_object_id: str) -> RailOperationResult:
        current = self._objects_by_id[provider_object_id].result.state
        if current == SettlementState.INITIATED:
            self.advance(provider_object_id, SettlementState.PROCESSING)
        return self.advance(provider_object_id, SettlementState.FAILED)

    def fail_late(self, provider_object_id: str) -> RailOperationResult:
        current = self._objects_by_id[provider_object_id].result.state
        if current != SettlementState.SETTLED:
            self.settle(provider_object_id)
        return self.advance(provider_object_id, SettlementState.FAILED_LATE)

    def webhook_payload(self, provider_object_id: str) -> bytes:
        stored = self._objects_by_id[provider_object_id]
        stored.event_counter += 1
        return json.dumps(
            {
                "event_id": f"evt_{provider_object_id}_{stored.event_counter}",
                "object_id": provider_object_id,
            },
            separators=(",", ":"),
        ).encode()

    def _create_or_reuse(
        self,
        *,
        idempotency_key: str,
        prefix: str,
        amount_minor: int | None,
        currency: str,
    ) -> RailOperationResult:
        existing_id = self._objects_by_idempotency_key.get(idempotency_key)
        if existing_id is not None:
            return self._objects_by_id[existing_id].result

        self._object_counter += 1
        provider_object_id = f"fake_{prefix}_{self._object_counter}"
        result = RailOperationResult(
            provider=ProviderName.FAKE,
            provider_object_id=provider_object_id,
            idempotency_key=idempotency_key,
            state=SettlementState.INITIATED,
            amount_minor=amount_minor,
            currency=currency,
        )
        self._objects_by_id[provider_object_id] = FakeRailObject(result=result)
        self._objects_by_idempotency_key[idempotency_key] = provider_object_id
        return result


def valid_transition(current: SettlementState, next_state: SettlementState) -> bool:
    allowed = {
        SettlementState.INITIATED: {SettlementState.PROCESSING},
        SettlementState.PROCESSING: {SettlementState.SETTLED, SettlementState.FAILED},
        SettlementState.SETTLED: {SettlementState.FAILED_LATE},
        SettlementState.FAILED: set(),
        SettlementState.FAILED_LATE: set(),
    }
    return next_state in allowed[current]
