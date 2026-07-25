"""Payments service over provider-plural rails."""

import structlog

from app.modules.payments.port import PaymentRailPort
from app.modules.payments.repo import PaymentsRepo
from app.modules.payments.types import (
    CollectionRequest,
    PaymentFlow,
    PayoutRequest,
    ProviderStatementLine,
    RailOperationResult,
    TopupRequest,
)

logger = structlog.get_logger(__name__)


class PaymentsService:
    def __init__(self, repo: PaymentsRepo) -> None:
        self.repo = repo

    async def create_topup(self, rail: PaymentRailPort, request: TopupRequest) -> RailOperationResult:
        result = await rail.create_topup(request)
        await self.repo.upsert_payment_object(flow=PaymentFlow.TOPUP, result=result)
        return result

    async def collect(
        self,
        rail: PaymentRailPort,
        request: CollectionRequest,
    ) -> RailOperationResult:
        result = await rail.collect(request)
        await self.repo.upsert_payment_object(flow=PaymentFlow.COLLECTION, result=result)
        return result

    async def send_payout(
        self,
        rail: PaymentRailPort,
        request: PayoutRequest,
    ) -> RailOperationResult:
        result = await rail.send_payout(request)
        await self.repo.upsert_payment_object(flow=PaymentFlow.PAYOUT, result=result)
        return result

    async def persist_webhook(
        self,
        rail: PaymentRailPort,
        *,
        headers: dict[str, str],
        body: bytes,
    ) -> bool:
        verification = await rail.verify_webhook(headers=headers, body=body)
        event = await self.repo.persist_partner_event(verification)
        return event is not None

    async def process_webhook_object(
        self,
        rail: PaymentRailPort,
        provider_object_id: str,
    ) -> RailOperationResult:
        result = await rail.get_settlement_status(provider_object_id)
        await self.repo.update_payment_state(
            provider=result.provider.value,
            provider_object_id=result.provider_object_id,
            state=result.state.value,
        )
        return result

    async def reconcile(self, rail: PaymentRailPort) -> list[ProviderStatementLine]:
        breaks: list[ProviderStatementLine] = []
        for line in await rail.statement_lines():
            payment_object = await self.repo.get_payment_object_by_idempotency_key(line.idempotency_key)
            if payment_object is None:
                breaks.append(line)
                await self.repo.create_recon_break(
                    provider=line.provider.value,
                    provider_object_id=line.provider_object_id,
                    idempotency_key=line.idempotency_key,
                    reason="missing_internal_payment_object",
                    details={
                        "amount_minor": line.amount_minor,
                        "currency": line.currency,
                        "state": line.state.value,
                    },
                )
                continue
            if payment_object.state != line.state.value:
                breaks.append(line)
                await self.repo.create_recon_break(
                    provider=line.provider.value,
                    provider_object_id=line.provider_object_id,
                    idempotency_key=line.idempotency_key,
                    reason="state_mismatch",
                    details={
                        "provider_state": line.state.value,
                        "internal_state": payment_object.state,
                    },
                )
        if breaks:
            logger.error("reconciliation_breaks_detected", count=len(breaks), provider=rail.provider)
        return breaks

