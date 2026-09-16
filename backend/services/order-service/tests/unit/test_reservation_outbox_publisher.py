"""ReservationOutboxPublisher pure helpers (issue #372, D6) — build_command
envelope shape and exponential backoff, по образцу
kernel_platform's `test_outbox_publisher.py`/`test_outbox_backoff.py`."""

import uuid
from datetime import UTC, datetime

from infrastructure.amqp.reservation_outbox_publisher import (
    build_command,
    compute_backoff,
)
from infrastructure.db.entity_configurations.models import ReservationOutboxModel


def _row(**overrides: object) -> ReservationOutboxModel:
    defaults: dict[str, object] = {
        "id": uuid.uuid4(),
        "order_id": uuid.uuid4(),
        "payload": {
            "order_id": str(uuid.uuid4()),
            "lines": [{"product_id": str(uuid.uuid4()), "quantity": 2}],
        },
        "created_at": datetime(2026, 9, 16, tzinfo=UTC),
    }
    defaults.update(overrides)
    return ReservationOutboxModel(**defaults)


def test_build_command_sets_command_id_and_causation_id_to_row_id() -> None:
    row = _row()

    command = build_command(row)

    assert command.command_id == row.id
    assert command.causation_id == row.id


def test_build_command_sets_command_type_to_inventory_reserve() -> None:
    command = build_command(_row())

    assert command.command_type == "inventory.reserve.v1"


def test_build_command_sets_correlation_id_to_order_id() -> None:
    order_id = uuid.uuid4()
    command = build_command(_row(order_id=order_id))

    assert command.correlation_id == str(order_id)


def test_build_command_forwards_the_stored_payload() -> None:
    payload = {"order_id": "x", "lines": [{"product_id": "y", "quantity": 1}]}
    command = build_command(_row(payload=payload))

    assert command.payload == payload


def test_compute_backoff_grows_exponentially_then_caps() -> None:
    first = compute_backoff(1).total_seconds()
    second = compute_backoff(2).total_seconds()
    capped = compute_backoff(50).total_seconds()

    assert second > first
    assert capped == compute_backoff(6).total_seconds()
