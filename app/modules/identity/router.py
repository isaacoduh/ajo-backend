"""Identity API routes."""

from typing import Annotated

from fastapi import APIRouter, Depends, status
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.rate_limit import USER_WRITE_RATE_LIMIT, enforce_rate_limit, rate_limit_auth
from app.db.session import get_session
from app.modules.identity.deps import get_current_user
from app.modules.identity.models import User
from app.modules.identity.repo import IdentityRepo
from app.modules.identity.schemas import (
    LoginRequest,
    LogoutRequest,
    RefreshRequest,
    RegisterRequest,
    TokenPairResponse,
    UserResponse,
)
from app.modules.identity.service import IdentityService, TokenPair
from app.modules.members.service import get_members_service
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


@router.post("/register", response_model=TokenPairResponse, status_code=status.HTTP_201_CREATED)
async def register(
    payload: RegisterRequest,
    service: Annotated[IdentityService, Depends(get_identity_service)],
) -> TokenPairResponse:
    return token_pair_response(await service.register(email=payload.email, password=payload.password))


@router.post("/login", response_model=TokenPairResponse)
async def login(
    payload: LoginRequest,
    service: Annotated[IdentityService, Depends(get_identity_service)],
) -> TokenPairResponse:
    return token_pair_response(await service.login(email=payload.email, password=payload.password))


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
