"""ADR 0031: platform exception handlers normalize every failure shape into
the structured `{"error": {"code", "message"}}` envelope."""

import httpx
import pytest
from fastapi import FastAPI, HTTPException
from pydantic import BaseModel

from kernel_platform.http.exception_handlers import register_error_handlers


class _DemoServiceError(Exception):
    """Stand-in for a service's own `ApplicationError` base (structural
    code/message/status_code, no inheritance from kernel_platform)."""

    code = "DEMO_UNAVAILABLE"
    message = "demo service недоступен"
    status_code = 503

    def __init__(self) -> None:
        super().__init__(self.message)


class _Body(BaseModel):
    price: float


def _build_app() -> FastAPI:
    app = FastAPI()
    register_error_handlers(app, service_error_type=_DemoServiceError)

    @app.get("/http-error")
    async def _http_error() -> None:
        raise HTTPException(status_code=401, detail="Требуется авторизация")

    @app.get("/http-error-with-headers")
    async def _http_error_with_headers() -> None:
        raise HTTPException(
            status_code=401,
            detail="Требуется авторизация",
            headers={"WWW-Authenticate": "Bearer"},
        )

    @app.post("/validate")
    async def _validate(body: _Body) -> dict[str, float]:
        return {"price": body.price}

    @app.get("/service-error")
    async def _service_error() -> None:
        raise _DemoServiceError()

    @app.get("/boom")
    async def _boom() -> None:
        raise RuntimeError("connection string: postgres://secret@host/db")

    return app


@pytest.fixture
def client() -> httpx.AsyncClient:
    # raise_app_exceptions=False: /boom deliberately lets an unhandled
    # exception reach the platform's catch-all — without this, ASGITransport
    # re-raises it into the test instead of returning the 500 the handler built.
    transport = httpx.ASGITransport(app=_build_app(), raise_app_exceptions=False)
    return httpx.AsyncClient(transport=transport, base_url="http://test")


async def test_http_exception_gets_canonical_code_and_original_status(
    client: httpx.AsyncClient,
) -> None:
    async with client:
        response = await client.get("/http-error")

    assert response.status_code == 401
    assert response.json() == {
        "error": {"code": "UNAUTHORIZED", "message": "Требуется авторизация"}
    }


async def test_http_exception_headers_are_preserved(client: httpx.AsyncClient) -> None:
    async with client:
        response = await client.get("/http-error-with-headers")

    assert response.headers["www-authenticate"] == "Bearer"


async def test_request_validation_error_becomes_structured_400_shape(
    client: httpx.AsyncClient,
) -> None:
    async with client:
        response = await client.post("/validate", json={"price": "not-a-number"})

    assert response.status_code == 422
    assert response.json() == {
        "error": {"code": "VALIDATION_ERROR", "message": "Некорректные данные запроса"}
    }


async def test_expected_service_error_uses_its_own_structural_contract(
    client: httpx.AsyncClient,
) -> None:
    async with client:
        response = await client.get("/service-error")

    assert response.status_code == 503
    assert response.json() == {
        "error": {"code": "DEMO_UNAVAILABLE", "message": "demo service недоступен"}
    }


async def test_unexpected_exception_is_hidden_behind_a_safe_500(
    client: httpx.AsyncClient,
) -> None:
    async with client:
        response = await client.get("/boom")

    assert response.status_code == 500
    body = response.json()
    assert body == {
        "error": {"code": "INTERNAL_ERROR", "message": "Внутренняя ошибка сервера"}
    }
    assert "secret" not in response.text
    assert "postgres://" not in response.text
