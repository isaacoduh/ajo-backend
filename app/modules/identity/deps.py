"""Identity route dependencies."""

from typing import Annotated

from fastapi import Depends
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer
from jwt import InvalidTokenError
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.errors import AppError
from app.core.security import decode_access_token
from app.db.session import get_session
from app.modules.identity.models import User
from app.modules.identity.repo import IdentityRepo

bearer_scheme = HTTPBearer(auto_error=False)


async def get_current_user(
    credentials: Annotated[HTTPAuthorizationCredentials | None, Depends(bearer_scheme)],
    session: Annotated[AsyncSession, Depends(get_session)],
) -> User:
    if credentials is None:
        raise unauthorized_error()
    try:
        claims = decode_access_token(credentials.credentials)
    except InvalidTokenError as exc:
        raise unauthorized_error() from exc

    user = await IdentityRepo(session).get_user_by_id(claims.user_id)
    if user is None or user.token_version != claims.token_version:
        raise unauthorized_error()
    return user


def unauthorized_error() -> AppError:
    return AppError(
        status_code=401,
        title="Unauthorized",
        detail="Authentication required.",
        type_="https://ajo.dev/problems/authentication-required",
    )
