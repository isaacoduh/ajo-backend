"""Guarded demo reset command."""

import asyncio
import os
import sys

from sqlalchemy import delete
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.config import Environment, get_settings
from app.db.base import Base
from app.db.model_registry import import_all_models
from app.db.session import session_scope
from app.tools.seed import SEED_EMAIL, SEED_PASSWORD, seed_m1, seed_m2_circle

CONFIRMATION = "destroy-and-reseed"
RESETTABLE_ENVS = {Environment.LOCAL, Environment.DEVELOPMENT, Environment.STAGING, Environment.TEST}


async def reset_product_data(session: AsyncSession) -> None:
    import_all_models()
    session.expunge_all()
    for table in reversed(Base.metadata.sorted_tables):
        await session.execute(delete(table))
    await session.flush()
    session.expunge_all()


async def reset_and_seed(session: AsyncSession) -> tuple[str, str, str]:
    await reset_product_data(session)
    m1_summary = await seed_m1(session)
    m2_circle_id = await seed_m2_circle(session)
    return str(m1_summary.member_id), str(m1_summary.user_id), str(m2_circle_id)


async def async_main() -> None:
    if os.getenv("DEMO_RESET_CONFIRM") != CONFIRMATION:
        print(
            "Refusing to reset demo data. Re-run with "
            f"DEMO_RESET_CONFIRM={CONFIRMATION}.",
            file=sys.stderr,
        )
        raise SystemExit(2)

    settings = get_settings()
    if settings.env == Environment.PRODUCTION:
        print("Refusing to reset demo data in production.", file=sys.stderr)
        raise SystemExit(2)
    if settings.env not in RESETTABLE_ENVS:
        print(f"Refusing to reset demo data in unsupported ENV={settings.env.value}.", file=sys.stderr)
        raise SystemExit(2)

    async for session in session_scope():
        member_id, user_id, circle_id = await reset_and_seed(session)
        print("Demo data reset and reseeded.")
        print(f"M1 login: email={SEED_EMAIL} password={SEED_PASSWORD}")
        print(f"M1 user_id={user_id} member_id={member_id}")
        print(f"M2 circle_id={circle_id}")


def main() -> None:
    asyncio.run(async_main())


if __name__ == "__main__":
    main()
