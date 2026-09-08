"""Fail-open OpenTelemetry setup shared by API processes."""

from __future__ import annotations

import logging
import os

from fastapi import FastAPI
from opentelemetry import trace
from opentelemetry.exporter.otlp.proto.grpc.trace_exporter import OTLPSpanExporter
from opentelemetry.instrumentation.fastapi import FastAPIInstrumentor
from opentelemetry.instrumentation.httpx import HTTPXClientInstrumentor
from opentelemetry.instrumentation.sqlalchemy import SQLAlchemyInstrumentor
from opentelemetry.sdk.resources import Resource
from opentelemetry.sdk.trace import TracerProvider
from opentelemetry.sdk.trace.export import BatchSpanProcessor
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker
from starlette.applications import Starlette

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
    """Add concise server spans to a FastAPI app.

    Prometheus scrapes and ASGI's per-chunk receive/send implementation spans
    are excluded; the request's server span and any child database spans remain.
    """
    provider = configure_tracing(service_name, endpoint=endpoint)
    if provider is None:
        return None

    FastAPIInstrumentor.instrument_app(
        app,
        tracer_provider=provider,
        # ASGI instrumentation matches excluded_urls against the *full* URL
        # (get_host_port_url_tuple), e.g. "http://catalog-api:8000/metrics"
        # — an anchored "^/metrics$" never matches that and silently traced
        # every scrape. No leading "^" so it matches regardless of scheme/host.
        excluded_urls=r"/metrics$",
        # Multipart uploads often arrive in several ASGI receive() calls and a
        # response may have separate start/body sends.  Those implementation
        # spans make a single request look duplicated in Tempo without adding
        # useful request-level observability.
        exclude_spans=["receive", "send"],
    )
    return provider


def instrument_httpx(*, tracer_provider: TracerProvider | None = None) -> None:
    """Trace every httpx client process-wide and propagate W3C trace context
    on outgoing requests. Without this, a call from one service to another
    (e.g. catalog-service's IdentityClient calling identity-service) never
    connects into one distributed trace — each service only ever sees its
    own inbound-request span, never the caller's. HTTPXClientInstrumentor
    patches the shared HTTPTransport/AsyncHTTPTransport classes, so it
    applies retroactively even to httpx.AsyncClient instances already
    constructed at module import time.

    `tracer_provider` defaults to the process-wide global (set by
    `configure_tracing`/`instrument_fastapi`) — pass one explicitly only to
    isolate a test from that global, process-wide singleton."""
    try:
        HTTPXClientInstrumentor().instrument(tracer_provider=tracer_provider)
    except Exception:
        logger.warning(
            "HTTPX tracing instrumentation is unavailable; continuing without it",
            exc_info=True,
        )


def instrument_sqlalchemy(
    app: Starlette,
    sessionmaker: async_sessionmaker[AsyncSession],
    *,
    tracer_provider: TracerProvider | None = None,
) -> None:
    """Turn SQL statements into child spans nested under the current HTTP
    span, so a slow request's trace shows which query was responsible —
    complements db_metrics.py's aggregate duration histogram, which can
    only say a service's queries got slower, not which one.

    Guarded like observability.db_metrics's own instrumentation: `lifespan`
    builds a fresh sessionmaker per entry, but repeated `TestClient(app)`
    entries in unit tests share one module-level `app` — instrumenting the
    same engine twice would double every query's spans."""
    if getattr(app.state, "_sqlalchemy_tracing_registered", False):
        return
    try:
        engine = sessionmaker.kw["bind"].sync_engine
        SQLAlchemyInstrumentor().instrument(
            engine=engine, tracer_provider=tracer_provider
        )
    except Exception:
        logger.warning(
            "SQLAlchemy tracing instrumentation is unavailable; continuing without it",
            exc_info=True,
        )
    app.state._sqlalchemy_tracing_registered = True
