"""Payments repository."""

from datetime import UTC, datetime
from uuid import UUID

from sqlalchemy import select, update
from sqlalchemy.ext.asyncio import AsyncSession

from app.modules.payments.models import PartnerEvent, PaymentObject, ReconBreak
from app.modules.payments.types import PaymentFlow, RailOperationResult, WebhookVerificationResult


class PaymentsRepo:
    def __init__(self, session: AsyncSession) -> None:
        self.session = session

    async def upsert_payment_object(
        self,
        *,
        flow: PaymentFlow,
        result: RailOperationResult,
    ) -> PaymentObject:
        existing = await self.get_payment_object(
            provider=result.provider.value,
            provider_object_id=result.provider_object_id,
        )
        if existing is not None:
            existing.state = result.state.value
            existing.amount_minor = result.amount_minor
            existing.currency = result.currency
            await self.session.flush()
            return existing

        payment_object = PaymentObject(
            provider=result.provider.value,
            provider_object_id=result.provider_object_id,
            flow=flow.value,
            idempotency_key=result.idempotency_key,
            state=result.state.value,
            amount_minor=result.amount_minor,
            currency=result.currency,
        )
        self.session.add(payment_object)
        await self.session.flush()
        return payment_object

    async def get_payment_object(
        self,
        *,
        provider: str,
        provider_object_id: str,
    ) -> PaymentObject | None:
        result = await self.session.execute(
            select(PaymentObject).where(
                PaymentObject.provider == provider,
                PaymentObject.provider_object_id == provider_object_id,
            )
        )
        return result.scalar_one_or_none()

    async def get_payment_object_by_idempotency_key(
        self,
        idempotency_key: str,
    ) -> PaymentObject | None:
        result = await self.session.execute(
            select(PaymentObject).where(PaymentObject.idempotency_key == idempotency_key)
        )
        return result.scalar_one_or_none()

    async def persist_partner_event(
        self,
        verification: WebhookVerificationResult,
    ) -> PartnerEvent | None:
        existing = await self.session.execute(
            select(PartnerEvent).where(
                PartnerEvent.provider == verification.provider.value,
                PartnerEvent.provider_event_id == verification.provider_event_id,
            )
        )
        if existing.scalar_one_or_none() is not None:
            return None
        event = PartnerEvent(
            provider=verification.provider.value,
            provider_event_id=verification.provider_event_id,
            provider_object_id=verification.provider_object_id,
            raw_payload=verification.raw_payload.decode(),
        )
        self.session.add(event)
        await self.session.flush()
        return event

    async def mark_partner_event_processed(self, event: PartnerEvent) -> None:
        event.processed_at = datetime.now(UTC)
        await self.session.flush()

    async def update_payment_state(
        self,
        *,
        provider: str,
        provider_object_id: str,
        state: str,
    ) -> None:
        await self.session.execute(
            update(PaymentObject)
            .where(
                PaymentObject.provider == provider,
                PaymentObject.provider_object_id == provider_object_id,
            )
            .values(state=state)
        )

    async def attach_journal_entry(
        self,
        *,
        payment_object: PaymentObject,
        journal_entry_id: UUID,
    ) -> PaymentObject:
        payment_object.journal_entry_id = journal_entry_id
        await self.session.flush()
        return payment_object

    async def create_recon_break(
        self,
        *,
        provider: str,
        provider_object_id: str,
        idempotency_key: str,
        reason: str,
        details: dict[str, object],
    ) -> ReconBreak:
        recon_break = ReconBreak(
            provider=provider,
            provider_object_id=provider_object_id,
            idempotency_key=idempotency_key,
            reason=reason,
            details=details,
        )
        self.session.add(recon_break)
        await self.session.flush()
        return recon_break
