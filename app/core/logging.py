"""Structured logging setup."""

import logging
import sys
from typing import Any

import structlog

from app.core.config import Settings
from app.core.observability import current_trace_context
from app.core.request_context import get_request_id


def add_request_id(
    logger: Any,
    method_name: str,
    event_dict: structlog.types.EventDict,
) -> structlog.types.EventDict:
    _ = logger, method_name
    request_id = get_request_id()
    if request_id is not None:
        event_dict["request_id"] = request_id
    return event_dict


def add_trace_context(
    logger: Any,
    method_name: str,
    event_dict: structlog.types.EventDict,
) -> structlog.types.EventDict:
    _ = logger, method_name
    event_dict.update(current_trace_context())
    return event_dict


def configure_logging(settings: Settings) -> None:
    logging.basicConfig(
        format="%(message)s",
        stream=sys.stdout,
        level=settings.log_level.upper(),
        force=True,
    )

    structlog.configure(
        processors=[
            structlog.contextvars.merge_contextvars,
            add_request_id,
            add_trace_context,
            structlog.processors.add_log_level,
            structlog.processors.TimeStamper(fmt="iso", utc=True),
            structlog.processors.StackInfoRenderer(),
            structlog.processors.format_exc_info,
            structlog.processors.JSONRenderer(),
        ],
        wrapper_class=structlog.make_filtering_bound_logger(
            logging.getLevelName(settings.log_level.upper())
        ),
        logger_factory=structlog.PrintLoggerFactory(file=sys.stdout),
        cache_logger_on_first_use=True,
    )
