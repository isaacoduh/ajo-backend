"""ARQ settings entrypoint.

The concrete job registry lands in the jobs pass. This class exists now so the
worker container can boot against the same settings surface as the API.
"""

from typing import ClassVar

from app.core.config import get_settings


async def startup(ctx: dict[str, object]) -> None:
    ctx["settings"] = get_settings()


class WorkerSettings:
    on_startup = startup
    functions: ClassVar[list[object]] = []
    cron_jobs: ClassVar[list[object]] = []
    max_tries = 5
