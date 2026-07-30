"""Payment route dependencies."""

from typing import Annotated

from fastapi import APIRouter, Depends
from sqlalchemy.ext.asyncio import AsyncSession

from app.db.session import get_session
from app.modules.payments.registry import PaymentRailRegistry, default_registry
from app.modules.payments.repo import PaymentsRepo
from app.modules.payments.service import PaymentsService

router = APIRouter(prefix="/payments", tags=["payments"])
SessionDep = Annotated[AsyncSession, Depends(get_session)]


def get_payments_service(session: SessionDep) -> PaymentsService:
    return PaymentsService(PaymentsRepo(session))


def get_payment_rail_registry() -> PaymentRailRegistry:
    return default_registry()
