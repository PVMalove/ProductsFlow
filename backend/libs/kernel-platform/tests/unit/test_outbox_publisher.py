# ruff: noqa: E501
import json
import uuid
from datetime import UTC, datetime
from typing import Any, cast

from aio_pika import DeliveryMode
from aio_pika.abc import AbstractExchange
from opentelemetry import trace
from opentelemetry.sdk.trace import TracerProvider
from opentelemetry.sdk.trace.export import SimpleSpanProcessor
from opentelemetry.sdk.trace.export.in_memory_span_exporter import InMemorySpanExporter

from kernel_platform.outbox.models import OutboxMessage
from kernel_platform.outbox.publisher import build_message, publish_message
from kernel_platform.outbox.trace_context import serialize_trace_context


def _row(**overrides: object) -> OutboxMessage:
    defaults: dict[str, object] = {
        "id": 42,
        "aggregate_type": "User",
        "aggregate_id": uuid.uuid4(),
        "event_type": "user.registered.v1",
        "payload": {"id": 7, "username": "alice"},
        "occurred_at": datetime(2026, 8, 29, tzinfo=UTC),
        "trace_context": "00-trace-01",
    }
    defaults.update(overrides)
    return OutboxMessage(**defaults)


def test_build_message_sets_message_id_to_row_id() -> None:
    message = build_message(_row(id=42))

    assert message.message_id == "42"


def test_build_message_sets_persistent_delivery_mode() -> None:
    message = build_message(_row())

    assert message.delivery_mode == DeliveryMode.PERSISTENT


def test_build_message_carries_traceparent_header() -> None:
    message = build_message(_row(trace_context="00-abc-01"))

    assert message.headers["traceparent"] == "00-abc-01"


def test_build_message_reads_json_trace_context_carrier() -> None:
    message = build_message(
        _row(
            trace_context=json.dumps(
                {"traceparent": "00-abc-01", "tracestate": "vendor=value"}
            )
        )
    )

    assert message.headers == {
        "traceparent": "00-abc-01",
        "tracestate": "vendor=value",
    }


async def test_publish_message_creates_child_span_and_injects_its_carrier(
    monkeypatch: Any,
) -> None:
    provider = TracerProvider()
    exporter = InMemorySpanExporter()
    provider.add_span_processor(SimpleSpanProcessor(exporter))
    monkeypatch.setattr(trace, "get_tracer_provider", lambda: provider)
    exchange = _RecordingExchange()

    with provider.get_tracer("test").start_as_current_span("http_request"):
        stored_carrier = json.loads(serialize_trace_context() or "")
    stored_carrier["tracestate"] = "vendor=value"
    row = _row(trace_context=json.dumps(stored_carrier))

    await publish_message(cast(AbstractExchange, exchange), row, timeout_seconds=5.0)

    message = exchange.messages[0]
    publisher_span = next(
        span for span in exporter.get_finished_spans() if span.name == "publish_message"
    )
    parent_span = next(
        span for span in exporter.get_finished_spans() if span.name == "http_request"
    )
    assert (
        message.headers["traceparent"].split("-")[1]
        == parent_span.context.trace_id.to_bytes(16, "big").hex()
    )
    assert publisher_span.parent is not None
    assert publisher_span.parent.span_id == parent_span.context.span_id
    assert publisher_span.context.trace_id == parent_span.context.trace_id
    assert (
        message.headers["traceparent"].split("-")[2]
        == publisher_span.context.span_id.to_bytes(8, "big").hex()
    )
    assert message.headers["tracestate"] == "vendor=value"


async def test_publish_message_accepts_legacy_plain_traceparent(
    monkeypatch: Any,
) -> None:
    provider = TracerProvider()
    monkeypatch.setattr(trace, "get_tracer_provider", lambda: provider)
    exchange = _RecordingExchange()

    with provider.get_tracer("test").start_as_current_span("http_request"):
        serialized_context = serialize_trace_context()
    legacy_traceparent = json.loads(serialized_context or "")["traceparent"]
    row = _row(trace_context=legacy_traceparent)

    await publish_message(cast(AbstractExchange, exchange), row, timeout_seconds=5.0)

    assert (
        exchange.messages[0].headers["traceparent"].split("-")[1]
        == (legacy_traceparent.split("-")[1])
    )


async def test_retry_publish_keeps_the_original_trace_id(
    monkeypatch: Any,
) -> None:
    provider = TracerProvider()
    monkeypatch.setattr(trace, "get_tracer_provider", lambda: provider)
    exchange = _RecordingExchange()

    with provider.get_tracer("test").start_as_current_span("http_request"):
        row = _row(trace_context=serialize_trace_context())

    await publish_message(cast(AbstractExchange, exchange), row, timeout_seconds=5.0)
    await publish_message(cast(AbstractExchange, exchange), row, timeout_seconds=5.0)

    trace_ids = [
        message.headers["traceparent"].split("-")[1] for message in exchange.messages
    ]
    assert trace_ids[0] == trace_ids[1]


class _RecordingExchange:
    def __init__(self) -> None:
        self.messages: list[Any] = []

    async def publish(self, message: Any, **_: Any) -> Any:
        self.messages.append(message)
        return None


def test_build_message_sets_type_to_event_type() -> None:
    message = build_message(_row(event_type="user.activated.v1"))

    assert message.type == "user.activated.v1"


def test_build_message_serializes_payload_as_json_body() -> None:
    message = build_message(_row(payload={"id": 7, "username": "alice"}))

    assert json.loads(message.body) == {"id": 7, "username": "alice"}
