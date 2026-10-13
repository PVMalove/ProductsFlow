"""CatalogClient.get_quote (issue #372, D9, Seams for TDD #5) — фейковый
httpx-транспорт: успех парсит unit_price_kopecks, любая ошибка (timeout/5xx/
4xx) схлопывается в единый QuoteResult.unavailable(), токен форвардится как
Bearer в исходящий запрос."""

import uuid

import httpx

from infrastructure.http.catalog_client import CatalogClient

BASE_URL = "http://catalog-api:8000"


def _client(handler) -> CatalogClient:
    transport = httpx.MockTransport(handler)
    http_client = httpx.AsyncClient(base_url=BASE_URL, transport=transport)
    return CatalogClient(http_client)


async def test_get_quote_success_parses_the_quote() -> None:
    product_id = uuid.uuid4()
    captured_requests: list[httpx.Request] = []

    def handler(request: httpx.Request) -> httpx.Response:
        captured_requests.append(request)
        return httpx.Response(
            200,
            json={
                "data": {
                    "product_id": str(product_id),
                    "unit_price_kopecks": 12_345,
                    "quantity": 2,
                }
            },
        )

    client = _client(handler)

    result = await client.get_quote(product_id, 2, bearer_token="user-token")

    assert result.ok is True
    assert result.line is not None
    assert result.line.product_id == product_id
    assert result.line.unit_price_kopecks == 12_345
    assert result.line.quantity == 2
    assert captured_requests[0].headers["authorization"] == "Bearer user-token"
    assert str(captured_requests[0].url).startswith(
        f"{BASE_URL}/api/v1/products/{product_id}/quote"
    )


async def test_get_quote_server_error_is_unavailable() -> None:
    def handler(_request: httpx.Request) -> httpx.Response:
        return httpx.Response(503)

    client = _client(handler)

    result = await client.get_quote(uuid.uuid4(), 1, bearer_token="t")

    assert result.ok is False
    assert result.line is None


async def test_get_quote_business_not_found_is_unavailable() -> None:
    """404/409 — товар удалён/скрыт/деактивирован (D9) — тот же единый исход,
    Scope clarification #2 подтверждена координатором."""

    def handler(_request: httpx.Request) -> httpx.Response:
        return httpx.Response(404)

    client = _client(handler)

    result = await client.get_quote(uuid.uuid4(), 1, bearer_token="t")

    assert result.ok is False


async def test_get_quote_transport_error_is_unavailable() -> None:
    def handler(request: httpx.Request) -> httpx.Response:
        raise httpx.ConnectError("catalog-api недоступен", request=request)

    client = _client(handler)

    result = await client.get_quote(uuid.uuid4(), 1, bearer_token="t")

    assert result.ok is False


async def test_get_quote_timeout_is_unavailable() -> None:
    def handler(request: httpx.Request) -> httpx.Response:
        raise httpx.TimeoutException("таймаут", request=request)

    client = _client(handler)

    result = await client.get_quote(uuid.uuid4(), 1, bearer_token="t")

    assert result.ok is False
