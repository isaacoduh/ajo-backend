"""Identity service."""

from dataclasses import dataclass
from uuid import UUID, uuid4

from sqlalchemy.exc import IntegrityError

from app.core.errors import AppError
from app.core.security import (
    REFRESH_TOKEN_TTL,
    create_access_token,
    generate_refresh_token,
    hash_password,
    hash_refresh_token,
    utc_now,
    verify_password,
)
from app.modules.identity.models import User
from app.modules.identity.repo import IdentityRepo
from app.modules.members.service import MembersService
from app.modules.screening.service import ScreeningService
from app.modules.wallets.service import WalletService


@dataclass(frozen=True)
class TokenPair:
    access_token: str
    refresh_token: str
    user: User


class IdentityService:
    def __init__(
        self,
        repo: IdentityRepo,
        screening_service: ScreeningService | None = None,
        members_service: MembersService | None = None,
        wallet_service: WalletService | None = None,
    ) -> None:
        self.repo = repo
        self.screening_service = screening_service
        self.members_service = members_service
        self.wallet_service = wallet_service

    async def register(
        self,
        *,
        email: str,
        password: str,
        display_name: str | None = None,
    ) -> TokenPair:
        password_hash = hash_password(password)
        try:
            user = await self.repo.create_user(email=email, password_hash=password_hash)
        except IntegrityError as exc:
            raise duplicate_email_error() from exc
        screening_state = "pending"
        if self.screening_service is not None:
            hits = await self.screening_service.screen_person(
                user_id=user.id,
                name=email,
                dob=None,
                country="GB",
            )
            screening_state = "review" if hits else "clear"
        if self.members_service is not None:
            member = await self.members_service.ensure_for_user(
                user_id=user.id,
                display_name=display_name or email,
                country="GB",
                screening_state=screening_state,
            )
            if self.wallet_service is not None:
                await self.wallet_service.ensure_for_member(member_id=member.id)
        return await self._issue_pair(user=user, family_id=uuid4())

    async def login(self, *, email: str, password: str) -> TokenPair:
        user = await self.repo.get_user_by_email(email)
        if user is None or not verify_password(password, user.password_hash):
            raise invalid_credentials_error()
        return await self._issue_pair(user=user, family_id=uuid4())

    async def refresh(self, *, refresh_token: str) -> TokenPair:
        token_hash = hash_refresh_token(refresh_token)
        stored = await self.repo.get_refresh_token_by_hash(token_hash)
        now = utc_now()
        if stored is None:
            raise invalid_refresh_error()
        if stored.revoked_at is not None or stored.replaced_by_token_id is not None:
            await self.repo.revoke_refresh_family(family_id=stored.family_id, revoked_at=now)
            raise invalid_refresh_error()
        if stored.expires_at <= now:
            await self.repo.revoke_refresh_family(family_id=stored.family_id, revoked_at=now)
            raise invalid_refresh_error()

        user = await self.repo.get_user_by_id(stored.user_id)
        if user is None:
            await self.repo.revoke_refresh_family(family_id=stored.family_id, revoked_at=now)
            raise invalid_refresh_error()

        token_pair = await self._issue_pair(user=user, family_id=stored.family_id)
        new_token_hash = hash_refresh_token(token_pair.refresh_token)
        new_stored = await self.repo.get_refresh_token_by_hash(new_token_hash)
        if new_stored is None:
            raise invalid_refresh_error()
        await self.repo.mark_refresh_token_used(
            token_id=stored.id,
            used_at=now,
            replaced_by_token_id=new_stored.id,
        )
        return token_pair

    async def logout(self, *, refresh_token: str) -> None:
        await self.repo.revoke_refresh_token(
            token_hash=hash_refresh_token(refresh_token),
            revoked_at=utc_now(),
        )

    async def logout_all(self, *, user_id: UUID) -> None:
        await self.repo.revoke_user_refresh_tokens(user_id=user_id, revoked_at=utc_now())

    async def _issue_pair(self, *, user: User, family_id: UUID) -> TokenPair:
        refresh_token = generate_refresh_token()
        await self.repo.create_refresh_token(
            user_id=user.id,
            family_id=family_id,
            token_hash=hash_refresh_token(refresh_token),
            expires_at=utc_now() + REFRESH_TOKEN_TTL,
        )
        access_token = create_access_token(user_id=user.id, token_version=user.token_version)
        return TokenPair(access_token=access_token, refresh_token=refresh_token, user=user)


def duplicate_email_error() -> AppError:
    return AppError(
        status_code=409,
        title="Conflict",
        detail="A user with that email already exists.",
        type_="https://ajo.dev/problems/email-already-registered",
    )


def invalid_credentials_error() -> AppError:
    return AppError(
        status_code=401,
        title="Unauthorized",
        detail="Invalid email or password.",
        type_="https://ajo.dev/problems/invalid-credentials",
    )


def invalid_refresh_error() -> AppError:
    return AppError(
        status_code=401,
        title="Unauthorized",
        detail="Invalid refresh token.",
        type_="https://ajo.dev/problems/invalid-refresh-token",
    )
