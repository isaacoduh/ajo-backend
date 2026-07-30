from collections.abc import AsyncIterator
from datetime import date
from uuid import UUID

import httpx
import pytest
from app.core.security import create_access_token
from app.db.ledger import AccountType, PostingSide, replay_balances
from app.db.session import get_session
from app.main import create_app
from app.modules.circles.service import draw_commitment_hash
from app.modules.identity.models import User
from app.modules.ledger.models import LedgerAccount, Posting
from app.modules.members.models import Member
from fastapi import FastAPI
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession


def app_for_session(db_session: AsyncSession) -> FastAPI:
    app = create_app()

    async def override_session() -> AsyncIterator[AsyncSession]:
        yield db_session

    app.dependency_overrides[get_session] = override_session
    return app


def auth_headers(user: User) -> dict[str, str]:
    token = create_access_token(user_id=user.id, token_version=user.token_version)
    return {"Authorization": f"Bearer {token}", "Idempotency-Key": f"test-{user.id}"}


async def create_member_user(
    db_session: AsyncSession,
    *,
    email: str,
) -> tuple[User, Member]:
    user = User(email=email, password_hash="hash")
    db_session.add(user)
    await db_session.flush()
    member = Member(
        user_id=user.id,
        display_name=email,
        country="GB",
        screening_state="clear",
    )
    db_session.add(member)
    await db_session.flush()
    return user, member


@pytest.mark.asyncio
async def test_circle_create_list_and_detail(
    test_env: None,
    db_session: AsyncSession,
) -> None:
    _ = test_env
    user, member = await create_member_user(db_session, email="owner@example.com")
    app = app_for_session(db_session)
    transport = httpx.ASGITransport(app=app)

    async with httpx.AsyncClient(transport=transport, base_url="http://test") as client:
        created = await client.post(
            "/circles",
            headers=auth_headers(user),
            json={
                "name": "Friday Esusu",
                "contribution_amount_minor": 2500,
                "member_count_target": 2,
                "cycle_count": 2,
                "cadence": "monthly",
                "start_date": str(date.today()),
            },
        )
        assert created.status_code == 201
        circle_id = created.json()["id"]

        listed = await client.get("/circles", headers=auth_headers(user))
        detail = await client.get(f"/circles/{circle_id}", headers=auth_headers(user))

    assert listed.status_code == 200
    assert listed.json()["items"][0]["id"] == circle_id
    assert detail.status_code == 200
    assert detail.json()["owner_member_id"] == str(member.id)
    assert detail.json()["members"] == [
        {
            "member_id": str(member.id),
            "role": "owner",
            "status": "active",
            "joined_at": detail.json()["members"][0]["joined_at"],
        }
    ]


@pytest.mark.asyncio
async def test_circle_lifecycle_collects_pays_out_and_records_late_failure(
    test_env: None,
    db_session: AsyncSession,
) -> None:
    _ = test_env
    users_and_members = [
        await create_member_user(db_session, email=f"m2-member-{index}@example.com")
        for index in range(8)
    ]
    owner_user, owner_member = users_and_members[0]
    app = app_for_session(db_session)
    transport = httpx.ASGITransport(app=app)

    async with httpx.AsyncClient(transport=transport, base_url="http://test") as client:
        created = await client.post(
            "/circles",
            headers=auth_headers(owner_user),
            json={
                "name": "Eight Member Circle",
                "contribution_amount_minor": 1000,
                "member_count_target": 8,
                "cycle_count": 8,
                "cadence": "monthly",
                "start_date": str(date.today()),
            },
        )
        assert created.status_code == 201
        circle_id = created.json()["id"]

        member_ids = [owner_member.id]
        for user, member in users_and_members[1:]:
            invite = await client.post(
                f"/circles/{circle_id}/invites",
                headers={**auth_headers(owner_user), "Idempotency-Key": f"invite-{member.id}"},
                json={"email": user.email},
            )
            assert invite.status_code == 201
            joined = await client.post(
                f"/circles/{circle_id}/join",
                headers=auth_headers(user),
                json={"token": invite.json()["token"]},
            )
            assert joined.status_code == 200
            member_ids.append(member.id)

        for user, _member in users_and_members:
            agreed = await client.post(
                f"/circles/{circle_id}/agreement",
                headers={**auth_headers(user), "Idempotency-Key": f"agree-{user.id}"},
                json={
                    "contribution_amount_minor": 1000,
                    "cadence": "monthly",
                    "start_date": str(date.today()),
                    "payout_rules": {"rule": "commit_reveal_order"},
                },
            )
            assert agreed.status_code == 200

        locked = await client.post(f"/circles/{circle_id}/lock", headers=auth_headers(owner_user))
        assert locked.status_code == 200
        assert locked.json()["state"] == "draw_pending"

        salt = "m2-demo-salt"
        commitment = draw_commitment_hash(circle_id=UUID(circle_id), member_ids=member_ids, salt=salt)
        committed = await client.post(
            f"/circles/{circle_id}/draw/commit",
            headers=auth_headers(owner_user),
            json={"commitment_hash": commitment},
        )
        assert committed.status_code == 200

        revealed = await client.post(
            f"/circles/{circle_id}/draw/reveal",
            headers=auth_headers(owner_user),
            json={"salt": salt},
        )
        assert revealed.status_code == 200
        assert len(revealed.json()["payout_order"]) == 8

        contributions = await client.get(f"/circles/{circle_id}/contributions", headers=auth_headers(owner_user))
        assert contributions.status_code == 200
        assert len(contributions.json()["items"]) == 64

        collected = await client.post(f"/circles/{circle_id}/collect-due", headers=auth_headers(owner_user))
        assert collected.status_code == 200
        paid_first_cycle = [
            item for item in collected.json()["items"] if item["status"] == "paid"
        ]
        assert len(paid_first_cycle) == 8
        cycle_id = paid_first_cycle[0]["cycle_id"]

        payout = await client.post(
            f"/circles/{circle_id}/cycles/{cycle_id}/payout",
            headers=auth_headers(owner_user),
        )
        assert payout.status_code == 200
        assert payout.json()["amount_minor"] == 8000

        failed = await client.post(
            f"/circles/{circle_id}/contributions/{paid_first_cycle[3]['id']}/fail-late",
            headers=auth_headers(owner_user),
        )
        assert failed.status_code == 200

        records = await client.get(f"/circles/{circle_id}/records", headers=auth_headers(owner_user))
        assert records.status_code == 200
        assert records.json() == {
            "arrears_count": 1,
            "shortfall_count": 1,
            "arrears_minor": 1000,
            "shortfall_minor": 1000,
        }

    await assert_ledger_replay_equals_materialized_balances(db_session)


async def assert_ledger_replay_equals_materialized_balances(db_session: AsyncSession) -> None:
    rows = await db_session.execute(
        select(
            Posting.account_id,
            LedgerAccount.account_type,
            Posting.side,
            Posting.amount_minor,
        ).join(LedgerAccount, Posting.account_id == LedgerAccount.id)
    )
    postings = [
        (
            account_id,
            AccountType(account_type),
            PostingSide(side),
            amount_minor,
        )
        for account_id, account_type, side, amount_minor in rows.all()
    ]
    replayed = replay_balances(postings)

    accounts = await db_session.execute(select(LedgerAccount))
    for account in accounts.scalars():
        assert account.balance_minor == replayed.get(account.id, 0)

    debit_total = sum(amount_minor for _account_id, _account_type, side, amount_minor in postings if side == PostingSide.DEBIT)
    credit_total = sum(amount_minor for _account_id, _account_type, side, amount_minor in postings if side == PostingSide.CREDIT)
    assert debit_total == credit_total
