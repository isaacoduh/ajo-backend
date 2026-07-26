"""Minimal OpenTelemetry setup."""

import os

import structlog
from fastapi import FastAPI
from opentelemetry import metrics, trace
from opentelemetry.exporter.otlp.proto.http.metric_exporter import OTLPMetricExporter
from opentelemetry.exporter.otlp.proto.http.trace_exporter import OTLPSpanExporter
from opentelemetry.instrumentation.fastapi import FastAPIInstrumentor
from opentelemetry.sdk.metrics import MeterProvider
from opentelemetry.sdk.metrics.export import PeriodicExportingMetricReader
from opentelemetry.sdk.resources import Resource
from opentelemetry.sdk.trace import TracerProvider
from opentelemetry.sdk.trace.export import BatchSpanProcessor

from app.core.config import Settings

logger = structlog.get_logger(__name__)

_CONFIGURED = False


def configure_observability(app: FastAPI, settings: Settings) -> None:
    """Configure optional OTLP tracing/metrics and FastAPI instrumentation."""
    global _CONFIGURED
    if not settings.otel_enabled:
        return

    if settings.otel_exporter_otlp_endpoint:
        os.environ.setdefault("OTEL_EXPORTER_OTLP_ENDPOINT", settings.otel_exporter_otlp_endpoint)
        if not _CONFIGURED:
            resource = Resource.create({"service.name": settings.otel_service_name})
            trace_provider = TracerProvider(resource=resource)
            trace_provider.add_span_processor(BatchSpanProcessor(OTLPSpanExporter()))
            trace.set_tracer_provider(trace_provider)

            metric_reader = PeriodicExportingMetricReader(OTLPMetricExporter())
            metrics.set_meter_provider(MeterProvider(resource=resource, metric_readers=[metric_reader]))
            _CONFIGURED = True
            logger.info(
                "otel_configured",
                service_name=settings.otel_service_name,
                otlp_endpoint=settings.otel_exporter_otlp_endpoint,
            )

    FastAPIInstrumentor.instrument_app(app)


def current_trace_context() -> dict[str, str]:
    span_context = trace.get_current_span().get_span_context()
    if not span_context.is_valid:
        return {}
    return {
        "trace_id": f"{span_context.trace_id:032x}",
        "span_id": f"{span_context.span_id:016x}",
    }
