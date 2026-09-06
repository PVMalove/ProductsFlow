from fastapi import FastAPI
from fastapi.responses import JSONResponse
from httpx import ASGITransport, AsyncClient
from opentelemetry.sdk.resources import Resource

from observability.context import span_id_var, trace_id_var
from observability.middleware import RequestContextMiddleware
from observability.tracing import build_tracer_provider


def test_builds_a_named_tracer_provider_with_a_bounded_batch_processor() -> None:
    provider = build_tracer_provider("catalog-service", endpoint="http://tempo:4317")

    resource = provider.resource
    assert isinstance(resource, Resource)
    assert resource.attributes["service.name"] == "catalog-service"

    processor = provider._active_span_processor._span_processors[0]._batch_processor  # type: ignore[attr-defined]
    assert processor._max_queue_size == 2048  # type: ignore[attr-defined]
    assert processor._max_export_batch_size == 512  # type: ignore[attr-defined]


def test_instrument_fastapi_excludes_metrics_endpoint() -> None:
    app = FastAPI()

    from observability.tracing import instrument_fastapi

    instrument_fastapi(app, "identity-service", endpoint="http://tempo:4317")

    assert app._is_instrumented_by_opentelemetry is True  # type: ignore[attr-defined]
    assert app.build_middleware_stack is not FastAPI.build_middleware_stack


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
