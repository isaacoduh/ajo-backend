"""Circles service skeleton."""

from app.modules.circles.repo import CirclesRepo
from app.modules.circles.schemas import PingResponse


class CirclesService:
    def __init__(self, repo: CirclesRepo) -> None:
        self.repo = repo

    async def ping(self) -> PingResponse:
        return PingResponse(module="circles", status=await self.repo.ping())

