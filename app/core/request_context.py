"""Request context carried through logs and responses."""

from contextvars import ContextVar, Token

REQUEST_ID_HEADER = "X-Request-ID"

request_id_var: ContextVar[str | None] = ContextVar("request_id", default=None)


def get_request_id() -> str | None:
    return request_id_var.get()


def set_request_id(value: str) -> Token[str | None]:
    return request_id_var.set(value)


def reset_request_id(token: Token[str | None]) -> None:
    request_id_var.reset(token)
