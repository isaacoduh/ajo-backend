"""Payment provider webhook routes."""

from typing import Annotated

from fastapi import APIRouter, Depends, Request, status
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.errors import AppError
from app.db.session import get_session
from app.modules.payments.registry import PaymentRailRegistry, default_registry
from app.modules.payments.repo import PaymentsRepo
from app.modules.payments.service import PaymentsService
from app.modules.payments.stripe_rail import (
    StripeConfigurationError,
    StripeRailError,
    StripeWebhookVerificationError,
)

router = APIRouter(prefix="/payments", tags=["payments"])
SessionDep = Annotated[AsyncSession, Depends(get_session)]


def get_payments_service(session: SessionDep) -> PaymentsService:
    return PaymentsService(PaymentsRepo(session))


def get_payment_rail_registry() -> PaymentRailRegistry:
    return default_registry()


@router.post("/webhooks/stripe", status_code=status.HTTP_200_OK)
async def stripe_webhook(
    request: Request,
    payments_service: Annotated[PaymentsService, Depends(get_payments_service)],
    registry: Annotated[PaymentRailRegistry, Depends(get_payment_rail_registry)],
) -> dict[str, bool]:
    rail = registry.by_name("stripe")
    body = await request.body()
    headers = dict(request.headers)
    try:
        inserted = await payments_service.persist_webhook(rail, headers=headers, body=body)
        if inserted:
            verification = await rail.verify_webhook(headers=headers, body=body)
            await payments_service.process_webhook_object(rail, verification.provider_object_id)
    except StripeWebhookVerificationError as exc:
        raise AppError(
            status_code=400,
            title="Invalid Stripe Webhook",
            detail=str(exc),
            type_="https://ajo.dev/problems/invalid-stripe-webhook",
        ) from exc
    except StripeConfigurationError as exc:
        raise AppError(
            status_code=503,
            title="Stripe Webhook Not Configured",
            detail=str(exc),
            type_="https://ajo.dev/problems/stripe-webhook-not-configured",
        ) from exc
    except StripeRailError as exc:
        raise AppError(
            status_code=502,
            title="Stripe Rail Error",
            detail=str(exc),
            type_="https://ajo.dev/problems/stripe-rail-error",
        ) from exc
    return {"received": True, "deduped": not inserted}
