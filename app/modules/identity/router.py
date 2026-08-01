"""Identity API routes."""

from typing import Annotated
from uuid import UUID

from fastapi import APIRouter, Depends, status
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.rate_limit import USER_WRITE_RATE_LIMIT, enforce_rate_limit, rate_limit_auth
from app.db.session import get_session
from app.modules.identity.deps import get_current_user
from app.modules.identity.models import User
from app.modules.identity.repo import IdentityRepo
from app.modules.identity.schemas import (
    AuthMeMemberResponse,
    AuthMeResponse,
    AuthMeUserResponse,
    ChangePasswordRequest,
    LoginRequest,
    LogoutRequest,
    RefreshRequest,
    RegisterRequest,
    SessionResponse,
    SessionsResponse,
    TokenPairResponse,
    UpdateMeRequest,
    UserResponse,
)
from app.modules.identity.service import IdentityService, TokenPair
from app.modules.members.service import MembersService, get_members_service
from app.modules.screening.service import get_screening_service
from app.modules.wallets.service import get_wallet_service

router = APIRouter(prefix="/auth", tags=["auth"], dependencies=[Depends(rate_limit_auth)])

SessionDep = Annotated[AsyncSession, Depends(get_session)]


def get_identity_service(session: SessionDep) -> IdentityService:
    return IdentityService(
        IdentityRepo(session),
        get_screening_service(session),
        get_members_service(session),
        get_wallet_service(session),
    )


def get_members_service_dep(session: SessionDep) -> MembersService:
    return get_members_service(session)


@router.post("/register", response_model=TokenPairResponse, status_code=status.HTTP_201_CREATED)
async def register(
    payload: RegisterRequest,
    service: Annotated[IdentityService, Depends(get_identity_service)],
) -> TokenPairResponse:
    return token_pair_response(
        await service.register(
            email=payload.email,
            password=payload.password,
            display_name=payload.display_name,
        )
    )


@router.post("/login", response_model=TokenPairResponse)
async def login(
    payload: LoginRequest,
    service: Annotated[IdentityService, Depends(get_identity_service)],
) -> TokenPairResponse:
    return token_pair_response(await service.login(email=payload.email, password=payload.password))


@router.get("/me", response_model=AuthMeResponse)
async def me(
    current_user: Annotated[User, Depends(get_current_user)],
    members_service: Annotated[MembersService, Depends(get_members_service_dep)],
) -> AuthMeResponse:
    member = await members_service.get_current_member(user_id=current_user.id)
    return AuthMeResponse(
        user=AuthMeUserResponse(id=current_user.id, email=current_user.email),
        member=AuthMeMemberResponse(
            id=member.id,
            display_name=member.display_name,
            country=member.country,
            screening_state=member.screening_state,
        ),
    )


@router.patch("/me", response_model=AuthMeResponse)
async def update_me(
    payload: UpdateMeRequest,
    current_user: Annotated[User, Depends(get_current_user)],
    members_service: Annotated[MembersService, Depends(get_members_service_dep)],
) -> AuthMeResponse:
    await enforce_rate_limit(identity=str(current_user.id), rate_limit=USER_WRITE_RATE_LIMIT)
    if "display_name" in payload.model_fields_set:
        member = await members_service.update_current_member_profile(
            user_id=current_user.id,
            display_name=payload.display_name,
            country=payload.country,
        )
    else:
        member = await members_service.update_current_member_profile(
            user_id=current_user.id,
            country=payload.country,
        )
    return AuthMeResponse(
        user=AuthMeUserResponse(id=current_user.id, email=current_user.email),
        member=AuthMeMemberResponse(
            id=member.id,
            display_name=member.display_name,
            country=member.country,
            screening_state=member.screening_state,
        ),
    )


@router.post("/refresh", response_model=TokenPairResponse)
async def refresh(
    payload: RefreshRequest,
    service: Annotated[IdentityService, Depends(get_identity_service)],
) -> TokenPairResponse:
    return token_pair_response(await service.refresh(refresh_token=payload.refresh_token))


@router.post("/logout", status_code=status.HTTP_204_NO_CONTENT)
async def logout(
    payload: LogoutRequest,
    service: Annotated[IdentityService, Depends(get_identity_service)],
) -> None:
    await service.logout(refresh_token=payload.refresh_token)


@router.post("/logout-all", status_code=status.HTTP_204_NO_CONTENT)
async def logout_all(
    current_user: Annotated[User, Depends(get_current_user)],
    service: Annotated[IdentityService, Depends(get_identity_service)],
) -> None:
    await enforce_rate_limit(identity=str(current_user.id), rate_limit=USER_WRITE_RATE_LIMIT)
    await service.logout_all(user_id=current_user.id)


@router.post("/change-password", status_code=status.HTTP_204_NO_CONTENT)
async def change_password(
    payload: ChangePasswordRequest,
    current_user: Annotated[User, Depends(get_current_user)],
    service: Annotated[IdentityService, Depends(get_identity_service)],
) -> None:
    await enforce_rate_limit(identity=str(current_user.id), rate_limit=USER_WRITE_RATE_LIMIT)
    await service.change_password(
        user_id=current_user.id,
        current_password=payload.current_password,
        new_password=payload.new_password,
    )


@router.get("/sessions", response_model=SessionsResponse)
async def list_sessions(
    current_user: Annotated[User, Depends(get_current_user)],
    service: Annotated[IdentityService, Depends(get_identity_service)],
) -> SessionsResponse:
    sessions = await service.list_sessions(user_id=current_user.id)
    return SessionsResponse(
        sessions=[
            SessionResponse(
                id=session.id,
                family_id=session.family_id,
                created_at=session.created_at,
                expires_at=session.expires_at,
                used_at=session.used_at,
                revoked_at=session.revoked_at,
                active=session.active,
            )
            for session in sessions
        ]
    )


@router.delete("/sessions/{session_id}", status_code=status.HTTP_204_NO_CONTENT)
async def revoke_session(
    session_id: UUID,
    current_user: Annotated[User, Depends(get_current_user)],
    service: Annotated[IdentityService, Depends(get_identity_service)],
) -> None:
    await enforce_rate_limit(identity=str(current_user.id), rate_limit=USER_WRITE_RATE_LIMIT)
    await service.revoke_session(user_id=current_user.id, session_id=session_id)


def token_pair_response(token_pair: TokenPair) -> TokenPairResponse:
    user = token_pair.user
    return TokenPairResponse(
        access_token=token_pair.access_token,
        refresh_token=token_pair.refresh_token,
        user=UserResponse(
            id=user.id,
            email=user.email,
            token_version=user.token_version,
            created_at=user.created_at,
        ),
    )
