"""Idempotency-Key middleware."""

import base64
import json
from collections.abc import Awaitable, Callable, Iterable
from dataclasses import dataclass
from typing import Any, Protocol, cast

import structlog
from fastapi import FastAPI
from redis.exceptions import RedisError
from starlette.middleware.base import BaseHTTPMiddleware
from starlette.requests import Request
from starlette.responses import Response
from starlette.types import ASGIApp

from app.core.errors import problem_response
from app.core.redis import get_redis

logger = structlog.get_logger(__name__)

IDEMPOTENCY_KEY_HEADER = "Idempotency-Key"
IDEMPOTENCY_TTL_SECONDS = 48 * 60 * 60
IDEMPOTENCY_LOCK_TTL_SECONDS = 60
MUTATING_METHODS = {"POST", "PUT", "PATCH", "DELETE"}
OPENAPI_MUTATING_METHODS = {method.lower() for method in MUTATING_METHODS}
IDEMPOTENCY_EXEMPT_PATH_PREFIXES = ("/payments/webhooks/",)

IDEMPOTENCY_KEY_OPENAPI_PARAMETER: dict[str, Any] = {
    "name": IDEMPOTENCY_KEY_HEADER,
    "in": "header",
    "required": True,
    "description": "Unique key for this mutation. Reuse it only when retrying the same request.",
    "schema": {"type": "string", "minLength": 1},
}


class IdempotencyStore(Protocol):
    async def get(self, key: str) -> str | None: ...

    async def set(
        self,
        key: str,
        value: str,
        ex: int | None = None,
        nx: bool = False,
    ) -> object: ...

    async def delete(self, key: str) -> object: ...


NextHandler = Callable[[Request], Awaitable[Response]]


@dataclass(frozen=True)
class StoredResponse:
    status_code: int
    headers: list[tuple[str, str]]
    body: bytes


class IdempotencyMiddleware(BaseHTTPMiddleware):
    def __init__(
        self,
        app: ASGIApp,
        *,
        store: IdempotencyStore | None = None,
    ) -> None:
        super().__init__(app)
        self.store = store

    async def dispatch(self, request: Request, call_next: NextHandler) -> Response:
        if request.method not in MUTATING_METHODS:
            return await call_next(request)
        if is_idempotency_exempt_path(request.url.path):
            return await call_next(request)

        idempotency_key = request.headers.get(IDEMPOTENCY_KEY_HEADER)
        if not idempotency_key:
            return problem_response(
                request=request,
                status_code=400,
                title="Bad Request",
                detail="Idempotency-Key is required for mutating requests.",
                type_="https://ajo.dev/problems/idempotency-key-required",
            )

        store = self.store if self.store is not None else get_redis()
        response_key = response_cache_key(request, idempotency_key)
        lock_key = lock_cache_key(request, idempotency_key)
        try:
            existing = await store.get(response_key)
            if existing is not None:
                return deserialize_response(existing)

            lock_acquired = await store.set(
                lock_key,
                "1",
                ex=IDEMPOTENCY_LOCK_TTL_SECONDS,
                nx=True,
            )
            if not lock_acquired:
                return problem_response(
                    request=request,
                    status_code=409,
                    title="Conflict",
                    detail="A request with this Idempotency-Key is already in progress.",
                    type_="https://ajo.dev/problems/idempotency-key-in-progress",
                )
        except RedisError:
            logger.exception(
                "idempotency_failed_open",
                method=request.method,
                path=request.url.path,
            )
            return await call_next(request)

        try:
            response = await call_next(request)
            stored = await stored_response_from_response(response)
            try:
                await store.set(
                    response_key,
                    serialize_response(stored),
                    ex=IDEMPOTENCY_TTL_SECONDS,
                )
            except RedisError:
                logger.exception(
                    "idempotency_store_failed_open",
                    method=request.method,
                    path=request.url.path,
                )
            return response_from_stored(stored)
        finally:
            try:
                await store.delete(lock_key)
            except RedisError:
                logger.exception(
                    "idempotency_lock_delete_failed",
                    method=request.method,
                    path=request.url.path,
                )


def configure_idempotency_openapi(app: FastAPI) -> None:
    """Expose the middleware's required header in interactive API documentation."""
    original_openapi = app.openapi

    def openapi() -> dict[str, Any]:
        schema = original_openapi()
        paths = schema.get("paths", {})
        for path_item in paths.values():
            if is_idempotency_exempt_path_from_openapi_item(paths, path_item):
                continue
            if not isinstance(path_item, dict):
                continue
            for method in OPENAPI_MUTATING_METHODS:
                operation = path_item.get(method)
                if not isinstance(operation, dict):
                    continue

                parameters = operation.setdefault("parameters", [])
                has_idempotency_key = any(
                    isinstance(parameter, dict)
                    and parameter.get("in") == "header"
                    and str(parameter.get("name", "")).lower()
                    == IDEMPOTENCY_KEY_HEADER.lower()
                    for parameter in parameters
                )
                if not has_idempotency_key:
                    parameters.append(IDEMPOTENCY_KEY_OPENAPI_PARAMETER.copy())

                responses = operation.setdefault("responses", {})
                responses.setdefault(
                    "400",
                    {"description": "Idempotency-Key header is required."},
                )
                responses.setdefault(
                    "409",
                    {"description": "A request with this Idempotency-Key is already in progress."},
                )
        return schema

    app.openapi = openapi  # type: ignore[method-assign]


def response_cache_key(request: Request, idempotency_key: str) -> str:
    return f"idempotency:response:{request.method}:{request.url.path}:{idempotency_key}"


def is_idempotency_exempt_path(path: str) -> bool:
    return any(path.startswith(prefix) for prefix in IDEMPOTENCY_EXEMPT_PATH_PREFIXES)


def is_idempotency_exempt_path_from_openapi_item(
    paths: dict[str, object],
    path_item: object,
) -> bool:
    for path, candidate in paths.items():
        if candidate is path_item and is_idempotency_exempt_path(path):
            return True
    return False


def lock_cache_key(request: Request, idempotency_key: str) -> str:
    return f"idempotency:lock:{request.method}:{request.url.path}:{idempotency_key}"


async def stored_response_from_response(response: Response) -> StoredResponse:
    body = b""
    async for chunk in cast(Any, response).body_iterator:
        body += chunk
    return StoredResponse(
        status_code=response.status_code,
        headers=list(string_headers(response.headers.items())),
        body=body,
    )


def string_headers(headers: Iterable[tuple[str, str]]) -> Iterable[tuple[str, str]]:
    for name, value in headers:
        if name.lower() == "content-length":
            continue
        yield name, value


def serialize_response(response: StoredResponse) -> str:
    return json.dumps(
        {
            "status_code": response.status_code,
            "headers": response.headers,
            "body": base64.b64encode(response.body).decode("ascii"),
        },
        separators=(",", ":"),
    )


def deserialize_response(value: str) -> Response:
    payload: dict[str, Any] = json.loads(value)
    stored = StoredResponse(
        status_code=int(payload["status_code"]),
        headers=[(str(name), str(header_value)) for name, header_value in payload["headers"]],
        body=base64.b64decode(str(payload["body"])),
    )
    return response_from_stored(stored)


def response_from_stored(stored: StoredResponse) -> Response:
    return Response(
        content=stored.body,
        status_code=stored.status_code,
        headers=dict(stored.headers),
    )
