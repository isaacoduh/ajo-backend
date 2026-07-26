"""Wallets service."""

from dataclasses import dataclass
from uuid import UUID

from sqlalchemy.ext.asyncio import AsyncSession

from app.core.security import utc_now
from app.db.ledger import AccountType
from app.modules.ledger.service import LedgerService
from app.modules.wallets.models import Wallet
from app.modules.wallets.repo import WalletsRepo

GBP = "GBP"
PLATFORM_SETTLEMENT_ACCOUNT_CODE = "platform:settlement:gbp"


@dataclass(frozen=True)
class WalletAccountCodes:
    pending: str
    available: str


class WalletService:
    def __init__(self, repo: WalletsRepo, ledger_service: LedgerService) -> None:
        self.repo = repo
        self.ledger_service = ledger_service

    async def ensure_for_member(self, *, member_id: UUID) -> Wallet:
        account_codes = wallet_account_codes(member_id)
        await self.ledger_service.ensure_account(
            code=PLATFORM_SETTLEMENT_ACCOUNT_CODE,
            name="Platform settlement GBP",
            account_type=AccountType.ASSET,
        )
        await self.ledger_service.ensure_account(
            code=account_codes.pending,
            name=f"Member {member_id} wallet pending GBP",
            account_type=AccountType.LIABILITY,
        )
        await self.ledger_service.ensure_account(
            code=account_codes.available,
            name=f"Member {member_id} wallet available GBP",
            account_type=AccountType.LIABILITY,
        )

        wallet = await self.repo.get_wallet_by_member_id(member_id)
        if wallet is not None:
            return wallet
        return await self.repo.create_wallet(
            member_id=member_id,
            pending_account_code=account_codes.pending,
            available_account_code=account_codes.available,
            provisioned_at=utc_now(),
        )


def get_wallet_service(session: AsyncSession) -> WalletService:
    return WalletService(WalletsRepo(session), LedgerService(session))


def wallet_account_codes(member_id: UUID) -> WalletAccountCodes:
    return WalletAccountCodes(
        pending=f"member:{member_id}:wallet:pending:gbp",
        available=f"member:{member_id}:wallet:available:gbp",
    )
