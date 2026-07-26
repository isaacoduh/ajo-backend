"""Wallets service."""

import base64
import json
from dataclasses import dataclass
from datetime import datetime
from typing import Any
from uuid import UUID

from sqlalchemy.ext.asyncio import AsyncSession

from app.core.errors import AppError
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


@dataclass(frozen=True)
class WalletBalance:
    currency: str
    available_minor: int
    pending_minor: int


@dataclass(frozen=True)
class WalletActivityItem:
    id: UUID
    journal_entry_id: UUID
    created_at: datetime
    description: str
    currency: str
    amount_minor: int
    direction: str
    wallet_balance_bucket: str


@dataclass(frozen=True)
class WalletActivityPage:
    items: list[WalletActivityItem]
    next_cursor: str | None


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

    async def balance_for_member(self, *, member_id: UUID) -> WalletBalance:
        wallet = await self.ensure_for_member(member_id=member_id)
        pending_account = await self.ledger_service.get_account_by_code(wallet.pending_account_code)
        available_account = await self.ledger_service.get_account_by_code(wallet.available_account_code)
        if pending_account is None or available_account is None:
            raise wallet_accounts_missing_error()
        return WalletBalance(
            currency=GBP,
            available_minor=available_account.balance_minor,
            pending_minor=pending_account.balance_minor,
        )

    async def activity_for_member(
        self,
        *,
        member_id: UUID,
        cursor: str | None,
        limit: int,
    ) -> WalletActivityPage:
        wallet = await self.ensure_for_member(member_id=member_id)
        decoded_cursor = decode_activity_cursor(cursor)
        rows = await self.ledger_service.list_account_activity(
            account_codes=[wallet.pending_account_code, wallet.available_account_code],
            limit=limit + 1,
            before_created_at=decoded_cursor.created_at if decoded_cursor is not None else None,
            before_posting_id=decoded_cursor.posting_id if decoded_cursor is not None else None,
        )
        page_rows = rows[:limit]
        next_cursor = None
        if len(rows) > limit:
            next_cursor = encode_activity_cursor(
                ActivityCursor(
                    created_at=page_rows[-1].journal_created_at,
                    posting_id=page_rows[-1].posting_id,
                )
            )
        return WalletActivityPage(
            items=[
                WalletActivityItem(
                    id=row.posting_id,
                    journal_entry_id=row.journal_entry_id,
                    created_at=row.journal_created_at,
                    description=row.journal_description,
                    currency=row.currency,
                    amount_minor=row.amount_minor,
                    direction=activity_direction(row.side),
                    wallet_balance_bucket=wallet_bucket(
                        row.account_code,
                        pending_account_code=wallet.pending_account_code,
                        available_account_code=wallet.available_account_code,
                    ),
                )
                for row in page_rows
            ],
            next_cursor=next_cursor,
        )


def get_wallet_service(session: AsyncSession) -> WalletService:
    return WalletService(WalletsRepo(session), LedgerService(session))


def wallet_account_codes(member_id: UUID) -> WalletAccountCodes:
    return WalletAccountCodes(
        pending=f"member:{member_id}:wallet:pending:gbp",
        available=f"member:{member_id}:wallet:available:gbp",
    )


@dataclass(frozen=True)
class ActivityCursor:
    created_at: datetime
    posting_id: UUID


def encode_activity_cursor(cursor: ActivityCursor) -> str:
    payload = {
        "created_at": cursor.created_at.isoformat(),
        "posting_id": str(cursor.posting_id),
    }
    encoded = base64.urlsafe_b64encode(
        json.dumps(payload, separators=(",", ":"), sort_keys=True).encode("utf-8")
    )
    return encoded.decode("ascii").rstrip("=")


def decode_activity_cursor(cursor: str | None) -> ActivityCursor | None:
    if cursor is None:
        return None
    try:
        padding = "=" * (-len(cursor) % 4)
        payload: Any = json.loads(base64.urlsafe_b64decode(f"{cursor}{padding}").decode("utf-8"))
        if not isinstance(payload, dict):
            raise ValueError
        created_at = datetime.fromisoformat(str(payload["created_at"]))
        posting_id = UUID(str(payload["posting_id"]))
    except (KeyError, TypeError, ValueError, json.JSONDecodeError) as exc:
        raise invalid_activity_cursor_error() from exc
    return ActivityCursor(created_at=created_at, posting_id=posting_id)


def activity_direction(side: str) -> str:
    if side == "credit":
        return "increase"
    return "decrease"


def wallet_bucket(
    account_code: str,
    *,
    pending_account_code: str,
    available_account_code: str,
) -> str:
    if account_code == pending_account_code:
        return "pending"
    if account_code == available_account_code:
        return "available"
    raise wallet_accounts_missing_error()


def invalid_activity_cursor_error() -> AppError:
    return AppError(
        status_code=400,
        title="Bad Request",
        detail="Wallet activity cursor is invalid.",
        type_="https://ajo.dev/problems/invalid-wallet-activity-cursor",
    )


def wallet_accounts_missing_error() -> AppError:
    return AppError(
        status_code=500,
        title="Wallet Accounts Missing",
        detail="Wallet ledger accounts are not provisioned.",
        type_="https://ajo.dev/problems/wallet-accounts-missing",
    )
