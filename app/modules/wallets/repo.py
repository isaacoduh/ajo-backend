"""Wallets repository."""

from datetime import datetime
from uuid import UUID

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.modules.wallets.models import Wallet


class WalletsRepo:
    def __init__(self, session: AsyncSession) -> None:
        self.session = session

    async def get_wallet_by_member_id(self, member_id: UUID) -> Wallet | None:
        result = await self.session.execute(select(Wallet).where(Wallet.member_id == member_id))
        return result.scalar_one_or_none()

    async def create_wallet(
        self,
        *,
        member_id: UUID,
        pending_account_code: str,
        available_account_code: str,
        provisioned_at: datetime,
    ) -> Wallet:
        wallet = Wallet(
            member_id=member_id,
            pending_account_code=pending_account_code,
            available_account_code=available_account_code,
            provisioned_at=provisioned_at,
        )
        self.session.add(wallet)
        await self.session.flush()
        return wallet
