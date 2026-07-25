"""Circles API routes."""

from typing import Annotated

from fastapi import APIRouter, Depends

from app.modules.circles.repo import CirclesRepo
from app.modules.circles.schemas import PingResponse
from app.modules.circles.service import CirclesService

router = APIRouter(prefix="/circles", tags=["circles"])


def get_circles_service() -> CirclesService:
    return CirclesService(CirclesRepo())


@router.get("/ping", response_model=PingResponse)
async def ping(
    service: Annotated[CirclesService, Depends(get_circles_service)],
) -> PingResponse:
    return await service.ping()
