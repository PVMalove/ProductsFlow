from fastapi import FastAPI
from fastapi.responses import JSONResponse
from httpx import ASGITransport, AsyncClient
from opentelemetry.instrumentation.httpx import HTTPXClientInstrumentor
from opentelemetry.sdk.resources import Resource
from opentelemetry.sdk.trace.export import SimpleSpanProcessor
from opentelemetry.sdk.trace.export.in_memory_span_exporter import InMemorySpanExporter
from sqlalchemy import text
from sqlalchemy.ext.asyncio import async_sessionmaker, create_async_engine
from starlette.applications import Starlette

from observability.context import span_id_var, trace_id_var
from observability.middleware import RequestContextMiddleware
from observability.tracing import (
    build_tracer_provider,
    instrument_httpx,
    instrument_sqlalchemy,
)


def test_builds_a_named_tracer_provider_with_a_bounded_batch_processor() -> None:
    provider = build_tracer_provider("catalog-service", endpoint="http://tempo:4317")

    resource = provider.resource
    assert isinstance(resource, Resource)
    assert resource.attributes["service.name"] == "catalog-service"

    processor = provider._active_span_processor._span_processors[0]._batch_processor  # type: ignore[attr-defined]
    assert processor._max_queue_size == 2048  # type: ignore[attr-defined]
    assert processor._max_export_batch_size == 512  # type: ignore[attr-defined]


async def test_instrument_fastapi_excludes_metrics_endpoint_from_actual_spans() -> None:
    """Regression test for excluded_urls being matched against the request's
    *full* URL (scheme://host:port/path — see get_host_port_url_tuple in
    opentelemetry-instrumentation-asgi), not just the path: an anchored
    "^/metrics$" silently never matched and traced every Prometheus scrape."""
    from observability.tracing import instrument_fastapi

    app = FastAPI()

    @app.get("/metrics")
    async def metrics() -> JSONResponse:
        return JSONResponse({})

    @app.get("/products")
    async def products() -> JSONResponse:
        return JSONResponse({})

    provider = instrument_fastapi(app, "identity-service", endpoint="http://tempo:4317")
    assert provider is not None
    exporter = InMemorySpanExporter()
    provider.add_span_processor(SimpleSpanProcessor(exporter))

    async with AsyncClient(
        transport=ASGITransport(app=app), base_url="http://test"
    ) as client:
        await client.get("/metrics")
        await client.get("/products")

    traced_paths = {
        (span.attributes or {}).get("http.target")
        for span in exporter.get_finished_spans()
    }
    assert "/products" in traced_paths
    assert "/metrics" not in traced_paths
    assert not any(
        (span.attributes or {}).get("asgi.event.type")
        in {"http.request", "http.response.start", "http.response.body"}
        for span in exporter.get_finished_spans()
    ), "ASGI receive/send implementation spans should not clutter traces"


async def test_http_span_ids_are_available_inside_request_context_middleware() -> None:
    app = FastAPI()

    @app.get("/trace")
    async def trace_context() -> JSONResponse:
        return JSONResponse(
            {"trace_id": trace_id_var.get(), "span_id": span_id_var.get()}
        )

    app.add_middleware(RequestContextMiddleware)
    from observability.tracing import instrument_fastapi

    instrument_fastapi(app, "test-api")

    async with AsyncClient(
        transport=ASGITransport(app=app), base_url="http://test"
    ) as client:
        response = await client.get("/trace")

    assert response.json()["trace_id"]
    assert response.json()["span_id"]


async def test_instrument_httpx_marks_the_process_as_instrumented() -> None:
    """opentelemetry-instrumentation-httpx's own test suite covers whether
    trace-context propagation actually works — ours just needs to prove we
    called the right entry point. HTTPXClientInstrumentor is a process-wide
    singleton (patches the shared HTTPTransport classes, not a per-instance
    client), so this uninstruments in a finally to avoid leaking instrumented
    httpx calls into unrelated tests."""
    instrumentor = HTTPXClientInstrumentor()
    assert instrumentor.is_instrumented_by_opentelemetry is False
    try:
        instrument_httpx()
        assert instrumentor.is_instrumented_by_opentelemetry is True
    finally:
        instrumentor.uninstrument()


async def test_instrument_sqlalchemy_traces_queries_as_child_spans_of_the_caller() -> (
    None
):
    provider = build_tracer_provider("catalog-service")
    exporter = InMemorySpanExporter()
    provider.add_span_processor(SimpleSpanProcessor(exporter))

    app = Starlette()
    sessionmaker = async_sessionmaker(
        create_async_engine("sqlite+aiosqlite:///:memory:"), expire_on_commit=False
    )
    try:
        instrument_sqlalchemy(app, sessionmaker, tracer_provider=provider)

        tracer = provider.get_tracer("test")
        with tracer.start_as_current_span("handler"):
            async with sessionmaker() as session:
                await session.execute(text("SELECT 1"))
    finally:
        from opentelemetry.instrumentation.sqlalchemy import SQLAlchemyInstrumentor

        SQLAlchemyInstrumentor().uninstrument()

    spans = exporter.get_finished_spans()
    parent_span = next(s for s in spans if s.name == "handler")
    parent_id = parent_span.context.span_id
    query_spans = [s for s in spans if s.parent and s.parent.span_id == parent_id]
    assert query_spans, (
        "expected the SQL statement to appear as a child span of 'handler'"
    )


async def test_instrument_sqlalchemy_skips_double_instrument_on_re_entry() -> None:
    """Mirrors db_metrics.py's own idempotency test — `lifespan` builds a
    fresh sessionmaker per entry, but repeated `TestClient(app)` entries in
    unit tests share one module-level `app`."""
    app = Starlette()
    provider = build_tracer_provider("identity-service")

    first_sessionmaker = async_sessionmaker(
        create_async_engine("sqlite+aiosqlite:///:memory:"), expire_on_commit=False
    )
    second_sessionmaker = async_sessionmaker(
        create_async_engine("sqlite+aiosqlite:///:memory:"), expire_on_commit=False
    )
    try:
        instrument_sqlalchemy(app, first_sessionmaker, tracer_provider=provider)
        instrument_sqlalchemy(app, second_sessionmaker, tracer_provider=provider)
    finally:
        from opentelemetry.instrumentation.sqlalchemy import SQLAlchemyInstrumentor

        SQLAlchemyInstrumentor().uninstrument()
