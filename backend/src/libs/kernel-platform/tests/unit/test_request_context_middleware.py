import logging
from typing import Any

import httpx
import pytest
from kernel_platform.logging.context import actor_id_var, request_id_var
from kernel_platform.logging.middleware import RequestContextMiddleware
from starlette.applications import Starlette
from starlette.requests import Request
from starlette.responses import JSONResponse
from starlette.routing import Route


class FakeTokenVerifier:
    def __init__(self, sub: int | None = None, raise_error: bool = False) -> None:
        self._sub = sub
        self._raise_error = raise_error

    async def verify_token(self, token: str) -> dict[str, Any]:
        if self._raise_error:
            raise ValueError("bad token")
        return {"sub": str(self._sub)}


async def _echo(_request: Request) -> JSONResponse:
    return JSONResponse(
        {"actor_id": actor_id_var.get(), "request_id": request_id_var.get()}
    )


async def _boom(_request: Request) -> JSONResponse:
    raise RuntimeError("boom")


def _build_client(verifier: FakeTokenVerifier) -> httpx.AsyncClient:
    # Middleware добавлена через add_middleware на само приложение (как в
    # реальном использовании identity-service), а не обёрнута снаружи
    # отдельного Starlette-инстанса — иначе необработанное исключение
    # маршрута гасится собственным ServerErrorMiddleware внутреннего
    # приложения раньше, чем долетит до dispatch() этой middleware.
    app = Starlette(routes=[Route("/echo", _echo), Route("/boom", _boom)])
    app.add_middleware(RequestContextMiddleware, verifier=verifier)
    return httpx.AsyncClient(
        transport=httpx.ASGITransport(app=app), base_url="http://test"
    )


async def test_generates_a_request_id_when_header_is_absent() -> None:
    async with _build_client(FakeTokenVerifier()) as client:
        response = await client.get("/echo")

    assert response.headers["x-request-id"]


async def test_echoes_the_request_id_header_when_present() -> None:
    async with _build_client(FakeTokenVerifier()) as client:
        response = await client.get("/echo", headers={"X-Request-ID": "given-id"})

    assert response.headers["x-request-id"] == "given-id"
    assert response.json()["request_id"] == "given-id"


async def test_actor_id_var_is_set_for_a_valid_bearer_token() -> None:
    async with _build_client(FakeTokenVerifier(sub=7)) as client:
        response = await client.get("/echo", headers={"Authorization": "Bearer token"})

    assert response.json()["actor_id"] == 7


async def test_request_is_not_blocked_and_actor_id_stays_none_without_a_bearer() -> (
    None
):
    async with _build_client(FakeTokenVerifier(sub=7)) as client:
        response = await client.get("/echo")

    assert response.status_code == 200
    assert response.json()["actor_id"] is None


async def test_actor_id_stays_none_and_request_is_not_blocked_for_invalid_bearer() -> (
    None
):
    async with _build_client(FakeTokenVerifier(raise_error=True)) as client:
        response = await client.get(
            "/echo", headers={"Authorization": "Bearer garbage"}
        )

    assert response.status_code == 200
    assert response.json()["actor_id"] is None


async def test_exactly_one_access_log_record_with_correct_fields(
    caplog: pytest.LogCaptureFixture,
) -> None:
    with caplog.at_level(logging.INFO, logger="kernel_platform.logging.middleware"):
        async with _build_client(FakeTokenVerifier()) as client:
            response = await client.get("/echo")

    records = [
        r for r in caplog.records if r.name == "kernel_platform.logging.middleware"
    ]
    assert len(records) == 1
    record = records[0]
    assert getattr(record, "method") == "GET"
    assert getattr(record, "path") == "/echo"
    assert getattr(record, "status_code") == response.status_code
    assert getattr(record, "duration_ms") >= 0


async def test_writes_exactly_one_access_log_record_when_the_handler_raises(
    caplog: pytest.LogCaptureFixture,
) -> None:
    with caplog.at_level(logging.INFO, logger="kernel_platform.logging.middleware"):
        async with _build_client(FakeTokenVerifier()) as client:
            with pytest.raises(RuntimeError):
                await client.get("/boom")

    records = [
        r for r in caplog.records if r.name == "kernel_platform.logging.middleware"
    ]
    assert len(records) == 1
    assert getattr(records[0], "path") == "/boom"
    assert getattr(records[0], "status_code") == 500

    assert actor_id_var.get() is None
    assert request_id_var.get() is None


async def test_context_vars_do_not_leak_between_requests() -> None:
    async with _build_client(FakeTokenVerifier(sub=7)) as client:
        first = await client.get("/echo", headers={"Authorization": "Bearer token"})
        assert first.json()["actor_id"] == 7

        second = await client.get("/echo")
        assert second.json()["actor_id"] is None

    assert actor_id_var.get() is None
    assert request_id_var.get() is None
