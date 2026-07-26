"""FastAPI application entrypoint."""

from collections.abc import AsyncIterator
from contextlib import asynccontextmanager

from fastapi import FastAPI, Request
from fastapi.responses import JSONResponse

from app.core.config import get_settings
from app.core.errors import PROBLEM_JSON, problem_response, register_error_handlers
from app.core.health import readiness_status
from app.core.idempotency import IdempotencyMiddleware
from app.core.logging import configure_logging
from app.core.middleware import RequestContextMiddleware
from app.modules.circles.router import router as circles_router
from app.modules.identity.router import router as identity_router
from app.modules.wallets.router import router as wallet_router


@asynccontextmanager
async def lifespan(app: FastAPI) -> AsyncIterator[None]:
    settings = get_settings()
    configure_logging(settings)
    app.state.settings = settings
    app.state.startup_summary = settings.redacted_startup_summary()
    yield


def create_app() -> FastAPI:
    settings = get_settings()
    application = FastAPI(title=settings.app_name, lifespan=lifespan)
    application.add_middleware(IdempotencyMiddleware)
    application.add_middleware(RequestContextMiddleware)
    register_error_handlers(application)
    application.include_router(circles_router)
    application.include_router(identity_router)
    application.include_router(wallet_router)

    @application.get("/healthz", tags=["health"])
    async def healthz() -> dict[str, str]:
        return {"status": "ok"}

    @application.get(
        "/readyz",
        tags=["health"],
        responses={503: {"content": {PROBLEM_JSON: {}}}},
    )
    async def readyz(request: Request) -> JSONResponse:
        status = await readiness_status()
        if status["status"] != "ok":
            return problem_response(
                request=request,
                status_code=503,
                title="Service Unavailable",
                detail="One or more dependencies are unavailable.",
                type_="https://ajo.dev/problems/readiness-check-failed",
                extra={"checks": status["checks"]},
            )
        return JSONResponse(status)

    return application


app = create_app()
