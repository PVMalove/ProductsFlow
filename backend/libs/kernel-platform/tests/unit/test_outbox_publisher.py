import json
from datetime import UTC, datetime

from aio_pika import DeliveryMode

from kernel_platform.outbox.models import OutboxMessage
from kernel_platform.outbox.publisher import build_message


def _row(**overrides: object) -> OutboxMessage:
    defaults: dict[str, object] = {
        "id": 42,
        "aggregate_type": "User",
        "aggregate_id": 7,
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


def test_build_message_sets_type_to_event_type() -> None:
    message = build_message(_row(event_type="user.activated.v1"))

    assert message.type == "user.activated.v1"


def test_build_message_serializes_payload_as_json_body() -> None:
    message = build_message(_row(payload={"id": 7, "username": "alice"}))

    assert json.loads(message.body) == {"id": 7, "username": "alice"}
