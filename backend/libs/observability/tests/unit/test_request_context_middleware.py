# ruff: noqa: E501
import logging
from typing import Any

import httpx
import pytest
from opentelemetry import trace
from opentelemetry.sdk.trace import TracerProvider
from opentelemetry.sdk.trace.export import SimpleSpanProcessor
from opentelemetry.sdk.trace.export.in_memory_span_exporter import InMemorySpanExporter
from starlette.applications import Starlette
from starlette.requests import Request
from starlette.responses import JSONResponse
from starlette.routing import Route

from observability.context import (
    actor_id_var,
    request_id_var,
    span_id_var,
    trace_id_var,
)
from observability.middleware import RequestContextMiddleware


class FakeTokenVerifier:
    def __init__(self, sub: int | str | None = None, raise_error: bool = False) -> None:
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


async def _metrics(_request: Request) -> JSONResponse:
    return JSONResponse({"ok": True})


def _build_client(verifier: FakeTokenVerifier) -> httpx.AsyncClient:
    # Middleware добавлена через add_middleware на само приложение (как в
    # реальном использовании identity-service), а не обёрнута снаружи
    # отдельного Starlette-инстанса — иначе необработанное исключение
    # маршрута гасится собственным ServerErrorMiddleware внутреннего
    # приложения раньше, чем долетит до dispatch() этой middleware.
    app = Starlette(
        routes=[
            Route("/echo", _echo),
            Route("/boom", _boom),
            Route("/metrics", _metrics),
        ]
    )
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


async def test_uuid_actor_id_is_preserved_for_a_valid_bearer_token() -> None:
    actor_id = "b6e4f82d-3b88-4f54-9ad0-b6d4a0ea9f0a"
    async with _build_client(FakeTokenVerifier(sub=actor_id)) as client:
        response = await client.get("/echo", headers={"Authorization": "Bearer token"})

    assert response.json()["actor_id"] == actor_id


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
    with caplog.at_level(logging.INFO, logger="observability.middleware"):
        async with _build_client(FakeTokenVerifier()) as client:
            response = await client.get("/echo")

    records = [r for r in caplog.records if r.name == "observability.middleware"]
    assert len(records) == 1
    record = records[0]
    assert getattr(record, "method") == "GET"
    assert getattr(record, "path") == "/echo"
    assert getattr(record, "status_code") == response.status_code
    assert getattr(record, "duration_ms") >= 0


async def test_logs_raw_x_user_id_and_x_user_role_headers(
    caplog: pytest.LogCaptureFixture,
) -> None:
    with caplog.at_level(logging.INFO, logger="observability.middleware"):
        async with _build_client(FakeTokenVerifier()) as client:
            await client.get(
                "/echo", headers={"X-User-Id": "attacker", "X-User-Role": "admin"}
            )

    records = [r for r in caplog.records if r.name == "observability.middleware"]
    assert len(records) == 1
    assert "x_user_id='attacker'" in records[0].getMessage()
    assert "x_user_role='admin'" in records[0].getMessage()


async def test_logs_empty_x_user_id_and_x_user_role_when_headers_are_absent(
    caplog: pytest.LogCaptureFixture,
) -> None:
    with caplog.at_level(logging.INFO, logger="observability.middleware"):
        async with _build_client(FakeTokenVerifier()) as client:
            await client.get("/echo")

    records = [r for r in caplog.records if r.name == "observability.middleware"]
    assert len(records) == 1
    assert "x_user_id=''" in records[0].getMessage()
    assert "x_user_role=''" in records[0].getMessage()


async def test_metrics_endpoint_produces_no_access_log_record(
    caplog: pytest.LogCaptureFixture,
) -> None:
    """Prometheus polls /metrics every scrape_interval — logging that on
    every scrape is noise, not application activity (mirrors /metrics being
    excluded from HTTP metrics and traces elsewhere)."""
    with caplog.at_level(logging.INFO, logger="observability.middleware"):
        async with _build_client(FakeTokenVerifier()) as client:
            response = await client.get("/metrics")

    assert response.status_code == 200
    records = [r for r in caplog.records if r.name == "observability.middleware"]
    assert records == []


async def test_writes_exactly_one_access_log_record_when_the_handler_raises(
    caplog: pytest.LogCaptureFixture,
) -> None:
    with caplog.at_level(logging.INFO, logger="observability.middleware"):
        async with _build_client(FakeTokenVerifier()) as client:
            with pytest.raises(RuntimeError):
                await client.get("/boom")

    records = [r for r in caplog.records if r.name == "observability.middleware"]
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


async def test_trace_context_is_bound_before_actor_id_resolution_can_log() -> None:
    """Regression test: `_set_actor_id` can itself log (a bearer token that
    fails verification) — if trace/span weren't bound yet by that point, that
    one log line would show trace_id/span_id as null while every other line
    for the same request has them, since it runs before the final access-log
    line in `finally`."""
    captured: dict[str, str | None] = {}

    class _CapturingVerifier(FakeTokenVerifier):
        async def verify_token(self, token: str) -> dict[str, Any]:
            captured["trace_id"] = trace_id_var.get()
            captured["span_id"] = span_id_var.get()
            raise ValueError("bad token")

    provider = TracerProvider()
    tracer = provider.get_tracer("test")
    with tracer.start_as_current_span("request") as span:
        with trace.use_span(span, end_on_exit=False):
            async with _build_client(_CapturingVerifier()) as client:
                await client.get("/echo", headers={"Authorization": "Bearer garbage"})

    assert captured["trace_id"] is not None
    assert captured["span_id"] is not None


async def test_active_trace_and_span_are_available_to_request_logs() -> None:
    exporter = InMemorySpanExporter()
    provider = TracerProvider()
    provider.add_span_processor(SimpleSpanProcessor(exporter))
    tracer = provider.get_tracer("test")
    with tracer.start_as_current_span("request") as span:
        with trace.use_span(span, end_on_exit=False):
            async with _build_client(FakeTokenVerifier()) as client:
                response = await client.get("/echo")

        assert response.json()["request_id"]
        assert trace_id_var.get() is None
        assert span_id_var.get() is None
        assert span.get_span_context().is_valid
