"""Fail-open OpenTelemetry setup shared by API processes."""

from __future__ import annotations

import logging
import os

from fastapi import FastAPI
from opentelemetry import trace
from opentelemetry.exporter.otlp.proto.grpc.trace_exporter import OTLPSpanExporter
from opentelemetry.instrumentation.fastapi import FastAPIInstrumentor
from opentelemetry.sdk.resources import Resource
from opentelemetry.sdk.trace import TracerProvider
from opentelemetry.sdk.trace.export import BatchSpanProcessor

logger = logging.getLogger(__name__)

_MAX_QUEUE_SIZE = 2048
_MAX_EXPORT_BATCH_SIZE = 512
_SCHEDULE_DELAY_MILLIS = 5000
_EXPORT_TIMEOUT_MILLIS = 5000


def build_tracer_provider(
    service_name: str, *, endpoint: str | None = None
) -> TracerProvider:
    """Build a bounded OTLP/gRPC provider without contacting the collector."""
    resource = Resource.create({"service.name": service_name})
    provider = TracerProvider(resource=resource)
    otlp_endpoint = endpoint or os.getenv("OTEL_EXPORTER_OTLP_TRACES_ENDPOINT")
    if otlp_endpoint is None:
        otlp_endpoint = os.getenv("OTEL_EXPORTER_OTLP_ENDPOINT")
    if otlp_endpoint:
        exporter = OTLPSpanExporter(
            endpoint=otlp_endpoint,
            insecure=True,
            timeout=_EXPORT_TIMEOUT_MILLIS / 1000,
        )
        provider.add_span_processor(
            BatchSpanProcessor(
                exporter,
                max_queue_size=_MAX_QUEUE_SIZE,
                max_export_batch_size=_MAX_EXPORT_BATCH_SIZE,
                schedule_delay_millis=_SCHEDULE_DELAY_MILLIS,
                export_timeout_millis=_EXPORT_TIMEOUT_MILLIS,
            )
        )
    return provider


def configure_tracing(
    service_name: str, *, endpoint: str | None = None
) -> TracerProvider | None:
    """Configure tracing for one process, keeping exporter failures fail-open."""
    try:
        provider = build_tracer_provider(service_name, endpoint=endpoint)
        current_provider = trace.get_tracer_provider()
        if current_provider.__class__.__name__ == "ProxyTracerProvider":
            trace.set_tracer_provider(provider)
        return provider
    except Exception:
        logger.warning(
            "OpenTelemetry tracing is unavailable; continuing without export",
            exc_info=True,
        )
        return None


def instrument_fastapi(
    app: FastAPI, service_name: str, *, endpoint: str | None = None
) -> TracerProvider | None:
    """Add server spans to a FastAPI app, excluding the Prometheus endpoint."""
    provider = configure_tracing(service_name, endpoint=endpoint)
    if provider is None:
        return None

    FastAPIInstrumentor.instrument_app(
        app,
        tracer_provider=provider,
        excluded_urls=r"^/metrics$",
    )
    return provider
