from uuid import uuid4

import pytest
from app.modules.identity.models import User
from app.modules.ledger.models import LedgerAccount
from app.modules.ledger.service import LedgerService
from app.modules.members.models import Member
from app.modules.wallets.models import Wallet
from app.modules.wallets.repo import WalletsRepo
from app.modules.wallets.service import (
    PLATFORM_SETTLEMENT_ACCOUNT_CODE,
    WalletService,
    wallet_account_codes,
)
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession


@pytest.mark.asyncio
async def test_wallet_provisioning_creates_member_wallet_accounts_once(
    db_session: AsyncSession,
) -> None:
    user = User(email="wallet-db@example.com", password_hash="hash")
    db_session.add(user)
    await db_session.flush()
    member = Member(
        user_id=user.id,
        display_name=user.email,
        country="GB",
        screening_state="clear",
    )
    db_session.add(member)
    await db_session.flush()
    service = WalletService(WalletsRepo(db_session), LedgerService(db_session))

    first = await service.ensure_for_member(member_id=member.id)
    second = await service.ensure_for_member(member_id=member.id)

    account_codes = wallet_account_codes(member.id)
    assert first.id == second.id
    assert first.member_id == member.id
    assert first.pending_account_code == account_codes.pending
    assert first.available_account_code == account_codes.available

    wallets = list((await db_session.execute(select(Wallet))).scalars())
    assert [wallet.id for wallet in wallets] == [first.id]

    accounts = list(
        (
            await db_session.execute(
                select(LedgerAccount).where(
                    LedgerAccount.code.in_(
                        [
                            PLATFORM_SETTLEMENT_ACCOUNT_CODE,
                            account_codes.pending,
                            account_codes.available,
                        ]
                    )
                )
            )
        ).scalars()
    )
    accounts_by_code = {account.code: account for account in accounts}
    assert set(accounts_by_code) == {
        PLATFORM_SETTLEMENT_ACCOUNT_CODE,
        account_codes.pending,
        account_codes.available,
    }
    assert accounts_by_code[PLATFORM_SETTLEMENT_ACCOUNT_CODE].account_type == "asset"
    assert accounts_by_code[account_codes.pending].account_type == "liability"
    assert accounts_by_code[account_codes.available].account_type == "liability"
    assert all(account.balance_minor == 0 for account in accounts)


def test_wallet_account_codes_are_deterministic() -> None:
    member_id = uuid4()

    first = wallet_account_codes(member_id)
    second = wallet_account_codes(member_id)

    assert first == second
    assert first.pending == f"member:{member_id}:wallet:pending:gbp"
    assert first.available == f"member:{member_id}:wallet:available:gbp"
