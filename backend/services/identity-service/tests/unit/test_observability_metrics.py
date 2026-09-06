import httpx

from api.main import app


async def test_metrics_endpoint_is_internal_and_not_self_instrumented() -> None:
    async with httpx.AsyncClient(
        transport=httpx.ASGITransport(app=app), base_url="http://test"
    ) as client:
        response = await client.get("/metrics")

    assert response.status_code == 200
    assert response.headers["content-type"].startswith("text/plain")
    assert (
        b"productsflow_identity_service_http_request_duration_seconds"
        in response.content
    )
    assert b'handler="/metrics"' not in response.content
