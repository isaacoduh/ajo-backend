"""RFC 9457 problem+json responses."""

from collections.abc import Mapping
from http import HTTPStatus
from typing import Any, cast

import structlog
from fastapi import FastAPI, Request
from fastapi.exceptions import RequestValidationError
from fastapi.responses import JSONResponse
from starlette.exceptions import HTTPException as StarletteHTTPException

from app.core.request_context import get_request_id

PROBLEM_JSON = "application/problem+json"

logger = structlog.get_logger(__name__)


class AppError(Exception):
    def __init__(
        self,
        *,
        status_code: int,
        title: str,
        detail: str,
        type_: str = "about:blank",
        extra: Mapping[str, Any] | None = None,
    ) -> None:
        self.status_code = status_code
        self.title = title
        self.detail = detail
        self.type = type_
        self.extra = dict(extra or {})


def problem_response(
    *,
    request: Request,
    status_code: int,
    title: str,
    detail: str,
    type_: str = "about:blank",
    extra: Mapping[str, Any] | None = None,
    headers: Mapping[str, str] | None = None,
) -> JSONResponse:
    body: dict[str, Any] = {
        "type": type_,
        "title": title,
        "status": status_code,
        "detail": detail,
        "instance": str(request.url.path),
    }
    trace_id = get_request_id()
    if trace_id is not None:
        body["trace_id"] = trace_id
    body.update(extra or {})
    return JSONResponse(
        status_code=status_code,
        content=body,
        headers=dict(headers or {}),
        media_type=PROBLEM_JSON,
    )


async def app_error_handler(request: Request, exc: AppError) -> JSONResponse:
    return problem_response(
        request=request,
        status_code=exc.status_code,
        title=exc.title,
        detail=exc.detail,
        type_=exc.type,
        extra=exc.extra,
    )


async def http_exception_handler(request: Request, exc: StarletteHTTPException) -> JSONResponse:
    status = HTTPStatus(exc.status_code)
    detail = exc.detail if isinstance(exc.detail, str) else status.phrase
    return problem_response(
        request=request,
        status_code=exc.status_code,
        title=status.phrase,
        detail=detail,
        headers=exc.headers,
    )


async def validation_exception_handler(
    request: Request,
    exc: RequestValidationError,
) -> JSONResponse:
    return problem_response(
        request=request,
        status_code=422,
        title="Unprocessable Content",
        detail="Request validation failed.",
        type_="https://ajo.dev/problems/validation-error",
        extra={"errors": exc.errors()},
    )


async def unhandled_exception_handler(request: Request, exc: Exception) -> JSONResponse:
    logger.exception("unhandled_exception", exc_info=exc)
    return problem_response(
        request=request,
        status_code=500,
        title="Internal Server Error",
        detail="An unexpected error occurred.",
        type_="https://ajo.dev/problems/internal-server-error",
    )


def register_error_handlers(app: FastAPI) -> None:
    app.add_exception_handler(Exception, unhandled_exception_handler)

    async def handle_app_error(request: Request, exc: Exception) -> JSONResponse:
        return await app_error_handler(request, cast(AppError, exc))

    async def handle_http_exception(request: Request, exc: Exception) -> JSONResponse:
        return await http_exception_handler(request, cast(StarletteHTTPException, exc))

    async def handle_validation_exception(request: Request, exc: Exception) -> JSONResponse:
        return await validation_exception_handler(request, cast(RequestValidationError, exc))

    app.add_exception_handler(AppError, handle_app_error)
    app.add_exception_handler(StarletteHTTPException, handle_http_exception)
    app.add_exception_handler(RequestValidationError, handle_validation_exception)
