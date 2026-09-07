from fastapi import FastAPI
from httpx import ASGITransport, AsyncClient
from prometheus_client import CollectorRegistry

from observability.metrics import register_http_metrics


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
