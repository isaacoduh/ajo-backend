from uuid import UUID, uuid4

import pytest
from app.core.errors import AppError
from app.db.ledger import (
    AccountType,
    PostingInput,
    PostingSide,
    account_delta,
    compute_entry_hash,
    replay_balances,
    validate_postings,
)
from hypothesis import given
from hypothesis import strategies as st


def test_validate_postings_rejects_unbalanced_entry() -> None:
    postings = [
        PostingInput(account_id=uuid4(), side=PostingSide.DEBIT, amount_minor=100),
        PostingInput(account_id=uuid4(), side=PostingSide.CREDIT, amount_minor=99),
    ]

    with pytest.raises(AppError) as exc_info:
        validate_postings(postings)

    assert exc_info.value.detail == "Journal entry is unbalanced."


def test_account_delta_respects_normal_balance_side() -> None:
    assert (
        account_delta(account_type=AccountType.ASSET, side=PostingSide.DEBIT, amount_minor=100)
        == 100
    )
    assert (
        account_delta(account_type=AccountType.ASSET, side=PostingSide.CREDIT, amount_minor=100)
        == -100
    )
    assert (
        account_delta(account_type=AccountType.LIABILITY, side=PostingSide.CREDIT, amount_minor=100)
        == 100
    )
    assert (
        account_delta(account_type=AccountType.LIABILITY, side=PostingSide.DEBIT, amount_minor=100)
        == -100
    )


def test_entry_hash_is_deterministic_and_chained() -> None:
    debit_account_id = uuid4()
    credit_account_id = uuid4()
    postings = [
        PostingInput(account_id=debit_account_id, side=PostingSide.DEBIT, amount_minor=100),
        PostingInput(account_id=credit_account_id, side=PostingSide.CREDIT, amount_minor=100),
    ]

    first = compute_entry_hash(
        idempotency_key="key-1",
        description="Contribution",
        previous_hash=None,
        postings=postings,
        reversed_entry_id=None,
    )
    reordered = compute_entry_hash(
        idempotency_key="key-1",
        description="Contribution",
        previous_hash=None,
        postings=list(reversed(postings)),
        reversed_entry_id=None,
    )
    chained = compute_entry_hash(
        idempotency_key="key-1",
        description="Contribution",
        previous_hash="a" * 64,
        postings=postings,
        reversed_entry_id=None,
    )

    assert first == reordered
    assert first != chained
    assert len(first) == 64


@given(
    amounts=st.lists(st.integers(min_value=1, max_value=100_000), min_size=1, max_size=25),
)
def test_replay_balances_equal_materialized_balances_for_valid_batches(amounts: list[int]) -> None:
    cash_account_id = UUID("00000000-0000-0000-0000-000000000001")
    liability_account_id = UUID("00000000-0000-0000-0000-000000000002")
    replay_input: list[tuple[UUID, AccountType, PostingSide, int]] = []
    materialized = {cash_account_id: 0, liability_account_id: 0}

    for amount in amounts:
        postings = [
            PostingInput(account_id=cash_account_id, side=PostingSide.DEBIT, amount_minor=amount),
            PostingInput(
                account_id=liability_account_id,
                side=PostingSide.CREDIT,
                amount_minor=amount,
            ),
        ]
        validate_postings(postings)
        replay_input.extend(
            [
                (cash_account_id, AccountType.ASSET, PostingSide.DEBIT, amount),
                (liability_account_id, AccountType.LIABILITY, PostingSide.CREDIT, amount),
            ]
        )
        materialized[cash_account_id] += amount
        materialized[liability_account_id] += amount

    assert replay_balances(replay_input) == materialized
