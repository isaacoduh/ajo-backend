"""Wallet API routes."""

from typing import Annotated

from fastapi import APIRouter, Depends, Header, Query, status
from sqlalchemy.ext.asyncio import AsyncSession

from app.db.session import get_session
from app.modules.identity.deps import get_current_user
from app.modules.identity.models import User
from app.modules.members.service import MembersService, get_members_service
from app.modules.wallets.schemas import (
    WalletActivityItemResponse,
    WalletActivityResponse,
    WalletBalanceResponse,
    WalletTopupRequest,
    WalletTopupResponse,
)
from app.modules.wallets.service import WalletService, get_wallet_service

router = APIRouter(prefix="/wallet", tags=["wallet"])

SessionDep = Annotated[AsyncSession, Depends(get_session)]


def get_members_service_dep(session: SessionDep) -> MembersService:
    return get_members_service(session)


def get_wallet_service_dep(session: SessionDep) -> WalletService:
    return get_wallet_service(session)


@router.get("/balance", response_model=WalletBalanceResponse)
async def balance(
    current_user: Annotated[User, Depends(get_current_user)],
    members_service: Annotated[MembersService, Depends(get_members_service_dep)],
    wallet_service: Annotated[WalletService, Depends(get_wallet_service_dep)],
) -> WalletBalanceResponse:
    member = await members_service.get_current_member(user_id=current_user.id)
    wallet_balance = await wallet_service.balance_for_member(member_id=member.id)
    return WalletBalanceResponse(
        currency=wallet_balance.currency,
        available_minor=wallet_balance.available_minor,
        pending_minor=wallet_balance.pending_minor,
    )


@router.get("/activity", response_model=WalletActivityResponse)
async def activity(
    current_user: Annotated[User, Depends(get_current_user)],
    members_service: Annotated[MembersService, Depends(get_members_service_dep)],
    wallet_service: Annotated[WalletService, Depends(get_wallet_service_dep)],
    cursor: Annotated[str | None, Query()] = None,
    limit: Annotated[int, Query(ge=1, le=100)] = 25,
) -> WalletActivityResponse:
    member = await members_service.get_current_member(user_id=current_user.id)
    page = await wallet_service.activity_for_member(
        member_id=member.id,
        cursor=cursor,
        limit=limit,
    )
    return WalletActivityResponse(
        items=[
            WalletActivityItemResponse(
                id=item.id,
                journal_entry_id=item.journal_entry_id,
                created_at=item.created_at,
                description=item.description,
                currency=item.currency,
                amount_minor=item.amount_minor,
                direction=item.direction,
                wallet_balance_bucket=item.wallet_balance_bucket,
            )
            for item in page.items
        ],
        next_cursor=page.next_cursor,
    )


@router.post("/topups", response_model=WalletTopupResponse, status_code=status.HTTP_201_CREATED)
async def create_topup(
    payload: WalletTopupRequest,
    current_user: Annotated[User, Depends(get_current_user)],
    members_service: Annotated[MembersService, Depends(get_members_service_dep)],
    wallet_service: Annotated[WalletService, Depends(get_wallet_service_dep)],
    idempotency_key: Annotated[str, Header(alias="Idempotency-Key")],
) -> WalletTopupResponse:
    member = await members_service.get_current_member(user_id=current_user.id)
    topup = await wallet_service.create_topup(
        member_id=member.id,
        user_id=current_user.id,
        amount_minor=payload.amount_minor,
        currency=payload.currency,
        idempotency_key=idempotency_key,
    )
    return WalletTopupResponse(
        id=topup.id,
        amount_minor=topup.amount_minor,
        currency=topup.currency,
        state=topup.state,
    )
