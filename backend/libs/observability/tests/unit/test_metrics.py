import asyncio

from fastapi import FastAPI
from httpx import ASGITransport, AsyncClient
from prometheus_client import CollectorRegistry

from observability.metrics import register_exception_metrics, register_http_metrics


async def test_registers_normalized_http_metrics_and_metrics_endpoint() -> None:
    app = FastAPI()

    @app.get("/products/{product_id}")
    async def get_product(product_id: int) -> dict[str, int]:
        return {"product_id": product_id}

    registry = CollectorRegistry()
    register_http_metrics(app, service_name="catalog-service", registry=registry)

    async with AsyncClient(
        transport=ASGITransport(app=app), base_url="http://test"
    ) as client:
        response = await client.get("/products/42")
        metrics = await client.get("/metrics")

    assert response.status_code == 200
    assert metrics.status_code == 200
    assert metrics.headers["content-type"].startswith("text/plain")
    body = metrics.text
    assert "http_request_duration_seconds" in body
    assert 'handler="/products/{product_id}"' in body
    assert 'handler="/products/42"' not in body
    assert 'handler="/metrics"' not in body
    assert "http_requests_inprogress" in body


async def test_inprogress_gauge_tracks_a_request_still_being_handled() -> None:
    app = FastAPI()
    started = asyncio.Event()
    release = asyncio.Event()

    @app.get("/slow")
    async def slow() -> dict[str, bool]:
        started.set()
        await release.wait()
        return {"ok": True}

    registry = CollectorRegistry()
    register_http_metrics(app, service_name="catalog-service", registry=registry)
    gauge_name = "productsflow_catalog_service_http_requests_inprogress"

    async with AsyncClient(
        transport=ASGITransport(app=app), base_url="http://test"
    ) as client:
        assert registry.get_sample_value(gauge_name) == 0

        pending = asyncio.ensure_future(client.get("/slow"))
        await started.wait()
        assert registry.get_sample_value(gauge_name) == 1

        release.set()
        response = await pending

    assert response.status_code == 200
    assert registry.get_sample_value(gauge_name) == 0


async def test_registering_metrics_is_idempotent() -> None:
    app = FastAPI()
    registry = CollectorRegistry()

    register_http_metrics(app, service_name="identity-service", registry=registry)
    register_http_metrics(app, service_name="identity-service", registry=registry)

    async with AsyncClient(
        transport=ASGITransport(app=app), base_url="http://test"
    ) as client:
        response = await client.get("/metrics")

    assert response.status_code == 200


def test_exception_metrics_records_a_count_labeled_by_type_and_service() -> None:
    registry = CollectorRegistry()
    record = register_exception_metrics("identity-service", registry=registry)

    record(ValueError("bad"))
    record(ValueError("bad again"))
    record(RuntimeError("boom"))

    assert (
        registry.get_sample_value(
            "productsflow_identity_service_http_exceptions_total",
            {"exception_type": "ValueError", "service": "identity-service"},
        )
        == 2
    )
    assert (
        registry.get_sample_value(
            "productsflow_identity_service_http_exceptions_total",
            {"exception_type": "RuntimeError", "service": "identity-service"},
        )
        == 1
    )
