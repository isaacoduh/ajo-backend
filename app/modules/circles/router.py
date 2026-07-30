"""Circles API routes."""

from typing import Annotated
from uuid import UUID

from fastapi import APIRouter, Depends, Header, status
from sqlalchemy.ext.asyncio import AsyncSession

from app.db.session import get_session
from app.modules.circles.schemas import (
    CircleAgreementListResponse,
    CircleAgreementRequest,
    CircleAgreementResponse,
    CircleContributionListResponse,
    CircleCreateRequest,
    CircleDetailResponse,
    CircleDrawCommitRequest,
    CircleDrawResponse,
    CircleDrawRevealRequest,
    CircleInviteRequest,
    CircleInviteResponse,
    CircleJoinRequest,
    CircleLedgerResponse,
    CircleListResponse,
    CirclePayoutResponse,
    CircleRecordsResponse,
    CircleStatementResponse,
    PingResponse,
)
from app.modules.circles.service import CirclesService, get_circles_service
from app.modules.identity.deps import get_current_user
from app.modules.identity.models import User
from app.modules.members.service import MembersService, get_members_service

router = APIRouter(prefix="/circles", tags=["circles"])

SessionDep = Annotated[AsyncSession, Depends(get_session)]


def get_circles_service_dep(session: SessionDep) -> CirclesService:
    return get_circles_service(session)


def get_members_service_dep(session: SessionDep) -> MembersService:
    return get_members_service(session)


async def current_member_id(
    current_user: Annotated[User, Depends(get_current_user)],
    members_service: Annotated[MembersService, Depends(get_members_service_dep)],
) -> UUID:
    return (await members_service.get_current_member(user_id=current_user.id)).id


@router.get("/ping", response_model=PingResponse)
async def ping(
    service: Annotated[CirclesService, Depends(get_circles_service_dep)],
) -> PingResponse:
    return await service.ping()


@router.post("", response_model=CircleDetailResponse, status_code=status.HTTP_201_CREATED)
async def create_circle(
    payload: CircleCreateRequest,
    member_id: Annotated[UUID, Depends(current_member_id)],
    service: Annotated[CirclesService, Depends(get_circles_service_dep)],
    idempotency_key: Annotated[str, Header(alias="Idempotency-Key")],
) -> CircleDetailResponse:
    _ = idempotency_key
    return await service.create_circle(
        owner_member_id=member_id,
        name=payload.name,
        contribution_amount_minor=payload.contribution_amount_minor,
        member_count_target=payload.member_count_target,
        cycle_count=payload.cycle_count,
        cadence=payload.cadence,
        start_date=payload.start_date,
    )


@router.get("", response_model=CircleListResponse)
async def list_circles(
    member_id: Annotated[UUID, Depends(current_member_id)],
    service: Annotated[CirclesService, Depends(get_circles_service_dep)],
) -> CircleListResponse:
    return CircleListResponse(items=await service.list_for_member(member_id=member_id))


@router.get("/{circle_id}", response_model=CircleDetailResponse)
async def circle_detail(
    circle_id: UUID,
    member_id: Annotated[UUID, Depends(current_member_id)],
    service: Annotated[CirclesService, Depends(get_circles_service_dep)],
) -> CircleDetailResponse:
    return await service.detail_for_member(circle_id=circle_id, member_id=member_id)


@router.post("/{circle_id}/invites", response_model=CircleInviteResponse, status_code=status.HTTP_201_CREATED)
async def create_invite(
    circle_id: UUID,
    payload: CircleInviteRequest,
    member_id: Annotated[UUID, Depends(current_member_id)],
    service: Annotated[CirclesService, Depends(get_circles_service_dep)],
    idempotency_key: Annotated[str, Header(alias="Idempotency-Key")],
) -> CircleInviteResponse:
    _ = idempotency_key
    invite = await service.create_invite(
        circle_id=circle_id,
        member_id=member_id,
        email=payload.email,
        expires_in_days=payload.expires_in_days,
    )
    return CircleInviteResponse(
        id=invite.id,
        circle_id=invite.circle_id,
        token=invite.token,
        email=invite.email,
        status=invite.status,
        expires_at=invite.expires_at,
    )


@router.post("/{circle_id}/join", response_model=CircleDetailResponse)
async def join_circle(
    circle_id: UUID,
    payload: CircleJoinRequest,
    member_id: Annotated[UUID, Depends(current_member_id)],
    service: Annotated[CirclesService, Depends(get_circles_service_dep)],
    idempotency_key: Annotated[str, Header(alias="Idempotency-Key")],
) -> CircleDetailResponse:
    _ = circle_id, idempotency_key
    return await service.join(token=payload.token, member_id=member_id)


@router.post("/{circle_id}/agreement", response_model=CircleAgreementResponse)
async def agree_terms(
    circle_id: UUID,
    payload: CircleAgreementRequest,
    member_id: Annotated[UUID, Depends(current_member_id)],
    service: Annotated[CirclesService, Depends(get_circles_service_dep)],
    idempotency_key: Annotated[str, Header(alias="Idempotency-Key")],
) -> CircleAgreementResponse:
    _ = idempotency_key
    agreement = await service.agree(
        circle_id=circle_id,
        member_id=member_id,
        contribution_amount_minor=payload.contribution_amount_minor,
        cadence=payload.cadence,
        start_date=payload.start_date,
        payout_rules=payload.payout_rules,
    )
    return CircleAgreementResponse(
        id=agreement.id,
        circle_id=agreement.circle_id,
        member_id=agreement.member_id,
        contribution_amount_minor=agreement.contribution_amount_minor,
        cadence=agreement.cadence,
        start_date=agreement.start_date,
        payout_rules=agreement.payout_rules,
        accepted_at=agreement.accepted_at,
    )


@router.get("/{circle_id}/agreement", response_model=CircleAgreementListResponse)
async def agreements(
    circle_id: UUID,
    member_id: Annotated[UUID, Depends(current_member_id)],
    service: Annotated[CirclesService, Depends(get_circles_service_dep)],
) -> CircleAgreementListResponse:
    return CircleAgreementListResponse(
        items=[
            CircleAgreementResponse(
                id=item.id,
                circle_id=item.circle_id,
                member_id=item.member_id,
                contribution_amount_minor=item.contribution_amount_minor,
                cadence=item.cadence,
                start_date=item.start_date,
                payout_rules=item.payout_rules,
                accepted_at=item.accepted_at,
            )
            for item in await service.list_agreements(circle_id=circle_id, member_id=member_id)
        ]
    )


@router.post("/{circle_id}/lock", response_model=CircleDetailResponse)
async def lock_circle(
    circle_id: UUID,
    member_id: Annotated[UUID, Depends(current_member_id)],
    service: Annotated[CirclesService, Depends(get_circles_service_dep)],
    idempotency_key: Annotated[str, Header(alias="Idempotency-Key")],
) -> CircleDetailResponse:
    _ = idempotency_key
    return await service.lock(circle_id=circle_id, member_id=member_id)


@router.post("/{circle_id}/draw/commit", response_model=CircleDrawResponse)
async def commit_draw(
    circle_id: UUID,
    payload: CircleDrawCommitRequest,
    member_id: Annotated[UUID, Depends(current_member_id)],
    service: Annotated[CirclesService, Depends(get_circles_service_dep)],
    idempotency_key: Annotated[str, Header(alias="Idempotency-Key")],
) -> CircleDrawResponse:
    _ = idempotency_key
    draw = await service.commit_draw(circle_id=circle_id, member_id=member_id, commitment_hash=payload.commitment_hash)
    return CircleDrawResponse(
        circle_id=draw.circle_id,
        commitment_hash=draw.commitment_hash,
        salt=draw.salt,
        revealed_at=draw.revealed_at,
        payout_order=[UUID(value) for value in draw.payout_order or []],
    )


@router.post("/{circle_id}/draw/reveal", response_model=CircleDrawResponse)
async def reveal_draw(
    circle_id: UUID,
    payload: CircleDrawRevealRequest,
    member_id: Annotated[UUID, Depends(current_member_id)],
    service: Annotated[CirclesService, Depends(get_circles_service_dep)],
    idempotency_key: Annotated[str, Header(alias="Idempotency-Key")],
) -> CircleDrawResponse:
    _ = idempotency_key
    draw = await service.reveal_draw(circle_id=circle_id, member_id=member_id, salt=payload.salt)
    return CircleDrawResponse(
        circle_id=draw.circle_id,
        commitment_hash=draw.commitment_hash,
        salt=draw.salt,
        revealed_at=draw.revealed_at,
        payout_order=[UUID(value) for value in draw.payout_order or []],
    )


@router.get("/{circle_id}/draw", response_model=CircleDrawResponse)
async def draw_detail(
    circle_id: UUID,
    member_id: Annotated[UUID, Depends(current_member_id)],
    service: Annotated[CirclesService, Depends(get_circles_service_dep)],
) -> CircleDrawResponse:
    draw = await service.get_draw_for_member(circle_id=circle_id, member_id=member_id)
    return CircleDrawResponse(
        circle_id=circle_id,
        commitment_hash=draw.commitment_hash if draw else None,
        salt=draw.salt if draw else None,
        revealed_at=draw.revealed_at if draw else None,
        payout_order=[UUID(value) for value in (draw.payout_order if draw else []) or []],
    )


@router.post("/{circle_id}/collect-due", response_model=CircleContributionListResponse)
async def collect_due(
    circle_id: UUID,
    member_id: Annotated[UUID, Depends(current_member_id)],
    service: Annotated[CirclesService, Depends(get_circles_service_dep)],
    idempotency_key: Annotated[str, Header(alias="Idempotency-Key")],
) -> CircleContributionListResponse:
    _ = idempotency_key
    await service.collect_due(circle_id=circle_id, member_id=member_id)
    return CircleContributionListResponse(items=await service.list_contributions(circle_id=circle_id, member_id=member_id))


@router.get("/{circle_id}/contributions", response_model=CircleContributionListResponse)
async def contributions(
    circle_id: UUID,
    member_id: Annotated[UUID, Depends(current_member_id)],
    service: Annotated[CirclesService, Depends(get_circles_service_dep)],
) -> CircleContributionListResponse:
    return CircleContributionListResponse(items=await service.list_contributions(circle_id=circle_id, member_id=member_id))


@router.post("/{circle_id}/cycles/{cycle_id}/payout", response_model=CirclePayoutResponse)
async def payout_cycle(
    circle_id: UUID,
    cycle_id: UUID,
    member_id: Annotated[UUID, Depends(current_member_id)],
    service: Annotated[CirclesService, Depends(get_circles_service_dep)],
    idempotency_key: Annotated[str, Header(alias="Idempotency-Key")],
) -> CirclePayoutResponse:
    _ = idempotency_key
    return await service.execute_payout(circle_id=circle_id, cycle_id=cycle_id, member_id=member_id)


@router.post("/{circle_id}/contributions/{contribution_id}/fail-late", response_model=CircleContributionListResponse)
async def fail_late(
    circle_id: UUID,
    contribution_id: UUID,
    member_id: Annotated[UUID, Depends(current_member_id)],
    service: Annotated[CirclesService, Depends(get_circles_service_dep)],
    idempotency_key: Annotated[str, Header(alias="Idempotency-Key")],
) -> CircleContributionListResponse:
    _ = idempotency_key
    await service.inject_late_failure(circle_id=circle_id, contribution_id=contribution_id, member_id=member_id)
    return CircleContributionListResponse(items=await service.list_contributions(circle_id=circle_id, member_id=member_id))


@router.get("/{circle_id}/ledger", response_model=CircleLedgerResponse)
async def circle_ledger(
    circle_id: UUID,
    member_id: Annotated[UUID, Depends(current_member_id)],
    service: Annotated[CirclesService, Depends(get_circles_service_dep)],
) -> CircleLedgerResponse:
    return CircleLedgerResponse(items=await service.ledger_for_member(circle_id=circle_id, member_id=member_id))


@router.get("/{circle_id}/statements/{period}", response_model=CircleStatementResponse)
async def circle_statement(
    circle_id: UUID,
    period: str,
    member_id: Annotated[UUID, Depends(current_member_id)],
    service: Annotated[CirclesService, Depends(get_circles_service_dep)],
) -> CircleStatementResponse:
    return await service.statement_for_member(circle_id=circle_id, member_id=member_id, period=period)


@router.get("/{circle_id}/records", response_model=CircleRecordsResponse)
async def records(
    circle_id: UUID,
    member_id: Annotated[UUID, Depends(current_member_id)],
    service: Annotated[CirclesService, Depends(get_circles_service_dep)],
) -> CircleRecordsResponse:
    return await service.records_for_member(circle_id=circle_id, member_id=member_id)


@router.post("/{circle_id}/complete", response_model=CircleDetailResponse)
async def complete(
    circle_id: UUID,
    member_id: Annotated[UUID, Depends(current_member_id)],
    service: Annotated[CirclesService, Depends(get_circles_service_dep)],
    idempotency_key: Annotated[str, Header(alias="Idempotency-Key")],
) -> CircleDetailResponse:
    _ = idempotency_key
    return await service.complete(circle_id=circle_id, member_id=member_id)
