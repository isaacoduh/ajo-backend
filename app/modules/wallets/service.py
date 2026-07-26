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
from app.db.ledger import AccountType, PostingInput, PostingSide
from app.modules.ledger.service import LedgerService
from app.modules.payments.models import PaymentObject
from app.modules.payments.registry import PaymentRailRegistry, default_registry
from app.modules.payments.repo import PaymentsRepo
from app.modules.payments.service import PaymentsService
from app.modules.payments.types import PaymentFlow, TopupRequest
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


@dataclass(frozen=True)
class WalletTopupResult:
    id: UUID
    amount_minor: int
    currency: str
    state: str
    journal_entry_id: UUID | None


class WalletService:
    def __init__(
        self,
        repo: WalletsRepo,
        ledger_service: LedgerService,
        payments_service: PaymentsService | None = None,
        rail_registry: PaymentRailRegistry | None = None,
    ) -> None:
        self.repo = repo
        self.ledger_service = ledger_service
        self.payments_service = payments_service
        self.rail_registry = rail_registry

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

    async def create_topup(
        self,
        *,
        member_id: UUID,
        user_id: UUID,
        amount_minor: int,
        currency: str,
        idempotency_key: str,
    ) -> WalletTopupResult:
        validate_money_command(amount_minor=amount_minor, currency=currency)
        wallet = await self.ensure_for_member(member_id=member_id)
        payment_object = await self._create_or_reuse_topup_payment(
            user_id=user_id,
            amount_minor=amount_minor,
            currency=currency,
            idempotency_key=idempotency_key,
        )
        validate_topup_replay(
            payment_object=payment_object,
            amount_minor=amount_minor,
            currency=currency,
        )
        if payment_object.journal_entry_id is not None:
            return wallet_topup_result(payment_object)

        platform_account = await self.ledger_service.get_account_by_code(
            PLATFORM_SETTLEMENT_ACCOUNT_CODE
        )
        pending_account = await self.ledger_service.get_account_by_code(wallet.pending_account_code)
        if platform_account is None or pending_account is None:
            raise wallet_accounts_missing_error()

        posted = await self.ledger_service.post_entry(
            idempotency_key=topup_initiated_journal_key(idempotency_key),
            description="Wallet top-up initiated",
            postings=[
                PostingInput(
                    account_id=platform_account.id,
                    side=PostingSide.DEBIT,
                    amount_minor=amount_minor,
                ),
                PostingInput(
                    account_id=pending_account.id,
                    side=PostingSide.CREDIT,
                    amount_minor=amount_minor,
                ),
            ],
        )
        await self._payments_service().attach_journal_entry(
            payment_object=payment_object,
            journal_entry_id=posted.journal_entry.id,
        )
        return wallet_topup_result(payment_object)

    async def _create_or_reuse_topup_payment(
        self,
        *,
        user_id: UUID,
        amount_minor: int,
        currency: str,
        idempotency_key: str,
    ) -> PaymentObject:
        existing = await self._payments_service().get_payment_object_by_idempotency_key(
            idempotency_key
        )
        if existing is not None:
            return existing
        return await self._payments_service().create_topup_object(
            self._rail_registry().for_flow(PaymentFlow.TOPUP),
            TopupRequest(
                idempotency_key=idempotency_key,
                user_id=str(user_id),
                amount_minor=amount_minor,
                currency=currency,
            ),
        )

    def _payments_service(self) -> PaymentsService:
        if self.payments_service is not None:
            return self.payments_service
        return PaymentsService(PaymentsRepo(self.repo.session))

    def _rail_registry(self) -> PaymentRailRegistry:
        if self.rail_registry is not None:
            return self.rail_registry
        return default_registry()


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


def validate_money_command(*, amount_minor: int, currency: str) -> None:
    if currency != GBP:
        raise AppError(
            status_code=422,
            title="Invalid Currency",
            detail="Wallet money movement supports GBP only.",
            type_="https://ajo.dev/problems/invalid-wallet-currency",
        )
    if amount_minor <= 0:
        raise AppError(
            status_code=422,
            title="Invalid Amount",
            detail="Wallet amount_minor must be positive.",
            type_="https://ajo.dev/problems/invalid-wallet-amount",
        )


def validate_topup_replay(
    *,
    payment_object: PaymentObject,
    amount_minor: int,
    currency: str,
) -> None:
    if (
        payment_object.flow != PaymentFlow.TOPUP.value
        or payment_object.amount_minor != amount_minor
        or payment_object.currency != currency
    ):
        raise AppError(
            status_code=409,
            title="Conflict",
            detail="Idempotency-Key was already used for a different payment command.",
            type_="https://ajo.dev/problems/payment-idempotency-key-conflict",
        )


def topup_initiated_journal_key(idempotency_key: str) -> str:
    return f"wallet-topup:{idempotency_key}:initiated"


def wallet_topup_result(payment_object: PaymentObject) -> WalletTopupResult:
    return WalletTopupResult(
        id=payment_object.id,
        amount_minor=payment_object.amount_minor or 0,
        currency=payment_object.currency,
        state=payment_object.state,
        journal_entry_id=payment_object.journal_entry_id,
    )


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
