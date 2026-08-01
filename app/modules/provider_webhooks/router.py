"""External provider webhook routes."""

from typing import Annotated

from fastapi import APIRouter, Depends, Request, status

from app.core.errors import AppError
from app.modules.circles.service import get_circles_service
from app.modules.payments.registry import PaymentRailRegistry
from app.modules.payments.router import (
    SessionDep,
    get_payment_rail_registry,
    get_payments_service,
)
from app.modules.payments.service import PaymentsService
from app.modules.payments.stripe_rail import (
    StripeConfigurationError,
    StripeRailError,
    StripeWebhookVerificationError,
)
from app.modules.payments.truelayer_rail import (
    TrueLayerConfigurationError,
    TrueLayerRailError,
    TrueLayerWebhookVerificationError,
)
from app.modules.wallets.service import get_wallet_service

router = APIRouter(prefix="/payments", tags=["payments"])


@router.post("/webhooks/stripe", status_code=status.HTTP_200_OK)
async def stripe_webhook(
    request: Request,
    session: SessionDep,
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
            result = await payments_service.process_webhook_object(
                rail,
                verification.provider_object_id,
            )
            wallet_service = get_wallet_service(session)
            await wallet_service.settle_topup_if_ready(
                provider=result.provider.value,
                provider_object_id=result.provider_object_id,
            )
            await wallet_service.settle_payout_if_ready(
                provider=result.provider.value,
                provider_object_id=result.provider_object_id,
            )
            circles_service = get_circles_service(session)
            await circles_service.settle_payout_if_ready(
                provider=result.provider.value,
                provider_object_id=result.provider_object_id,
            )
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


@router.post("/webhooks/truelayer", status_code=status.HTTP_200_OK)
async def truelayer_webhook(
    request: Request,
    session: SessionDep,
    payments_service: Annotated[PaymentsService, Depends(get_payments_service)],
    registry: Annotated[PaymentRailRegistry, Depends(get_payment_rail_registry)],
) -> dict[str, bool]:
    rail = registry.by_name("truelayer")
    body = await request.body()
    headers = dict(request.headers)
    try:
        inserted = await payments_service.persist_webhook(rail, headers=headers, body=body)
        if inserted:
            verification = await rail.verify_webhook(headers=headers, body=body)
            result = await payments_service.process_webhook_object(
                rail,
                verification.provider_object_id,
            )
            wallet_service = get_wallet_service(session)
            await wallet_service.settle_topup_if_ready(
                provider=result.provider.value,
                provider_object_id=result.provider_object_id,
            )
            await wallet_service.settle_payout_if_ready(
                provider=result.provider.value,
                provider_object_id=result.provider_object_id,
            )
            circles_service = get_circles_service(session)
            await circles_service.settle_payout_if_ready(
                provider=result.provider.value,
                provider_object_id=result.provider_object_id,
            )
    except TrueLayerWebhookVerificationError as exc:
        raise AppError(
            status_code=400,
            title="Invalid TrueLayer Webhook",
            detail=str(exc),
            type_="https://ajo.dev/problems/invalid-truelayer-webhook",
        ) from exc
    except TrueLayerConfigurationError as exc:
        raise AppError(
            status_code=503,
            title="TrueLayer Webhook Not Configured",
            detail=str(exc),
            type_="https://ajo.dev/problems/truelayer-webhook-not-configured",
        ) from exc
    except TrueLayerRailError as exc:
        raise AppError(
            status_code=502,
            title="TrueLayer Rail Error",
            detail=str(exc),
            type_="https://ajo.dev/problems/truelayer-rail-error",
        ) from exc
    return {"received": True, "deduped": not inserted}
