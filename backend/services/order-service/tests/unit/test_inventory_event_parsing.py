"""Чистая функция парсинга `inventory.reserved.v1` (issue #372, D7), по
образцу inventory-worker's `parse_product_created_snapshot` — толерантна к
лишним полям снапшота, нужны только `order_id`/`confirmed_lines[].product_id`
(`unavailable_lines` не нужен для применения результата к Order/Cart)."""

import json
import uuid

import pytest

from api.workers.commands.inventory_event_handler import (
    parse_allocation_result,
    parse_reservation_release,
    parse_reservation_result,
)
from domain.entities.order import ReleaseReason


def test_parse_reservation_result_extracts_order_id_and_confirmed_product_ids() -> None:
    order_id = uuid.uuid4()
    confirmed_product_id = uuid.uuid4()
    body = json.dumps(
        {
            "order_id": str(order_id),
            "expires_at": "2026-01-01T00:00:00+00:00",
            "confirmed_lines": [
                {"product_id": str(confirmed_product_id), "quantity": 1}
            ],
            "unavailable_lines": [
                {"product_id": str(uuid.uuid4()), "requested_quantity": 2}
            ],
        }
    ).encode()

    command = parse_reservation_result(body)

    assert command.order_id == order_id
    assert command.confirmed_product_ids == frozenset({confirmed_product_id})


def test_parse_reservation_result_zero_confirmed_lines_is_an_empty_set() -> None:
    order_id = uuid.uuid4()
    body = json.dumps(
        {
            "order_id": str(order_id),
            "expires_at": "2026-01-01T00:00:00+00:00",
            "confirmed_lines": [],
            "unavailable_lines": [
                {"product_id": str(uuid.uuid4()), "requested_quantity": 1}
            ],
        }
    ).encode()

    command = parse_reservation_result(body)

    assert command.confirmed_product_ids == frozenset()


def test_parse_reservation_result_rejects_missing_order_id() -> None:
    with pytest.raises(ValueError):
        parse_reservation_result(json.dumps({"confirmed_lines": []}).encode())


def test_parse_reservation_result_rejects_invalid_json() -> None:
    with pytest.raises(ValueError):
        parse_reservation_result(b"not-json")


def test_parse_reservation_result_rejects_non_object_payload() -> None:
    with pytest.raises(ValueError):
        parse_reservation_result(json.dumps([1, 2, 3]).encode())


@pytest.mark.parametrize(
    ("reason", "expected"),
    [("manual", ReleaseReason.MANUAL), ("expired", ReleaseReason.EXPIRED)],
)
def test_parse_reservation_release_extracts_order_id_and_reason(
    reason: str, expected: ReleaseReason
) -> None:
    order_id = uuid.uuid4()
    body = json.dumps(
        {
            "order_id": str(order_id),
            "reason": reason,
            "released_lines": [{"product_id": str(uuid.uuid4()), "quantity": 1}],
        }
    ).encode()

    command = parse_reservation_release(body)

    assert command.order_id == order_id
    assert command.reason is expected


def test_parse_reservation_release_rejects_missing_order_id() -> None:
    with pytest.raises(ValueError):
        parse_reservation_release(json.dumps({"reason": "expired"}).encode())


@pytest.mark.parametrize(
    "payload",
    [
        {"released_lines": []},
        {"reason": "cancelled", "released_lines": []},
        {"reason": ["expired"], "released_lines": []},
    ],
    ids=["missing_reason", "unknown_reason", "non_string_reason"],
)
def test_parse_reservation_release_treats_anything_but_expired_as_a_plain_release(
    payload: dict[str, object],
) -> None:
    order_id = uuid.uuid4()

    command = parse_reservation_release(
        json.dumps({"order_id": str(order_id), **payload}).encode()
    )

    assert command.order_id == order_id
    assert command.reason is ReleaseReason.MANUAL


def test_parse_reservation_release_rejects_invalid_json() -> None:
    with pytest.raises(ValueError):
        parse_reservation_release(b"not-json")


def test_parse_allocation_result_extracts_order_id() -> None:
    order_id = uuid.uuid4()
    body = json.dumps(
        {
            "order_id": str(order_id),
            "allocated_lines": [{"product_id": str(uuid.uuid4()), "quantity": 2}],
        }
    ).encode()

    command = parse_allocation_result(body)

    assert command.order_id == order_id


def test_parse_allocation_result_rejects_missing_order_id() -> None:
    with pytest.raises(ValueError):
        parse_allocation_result(json.dumps({"allocated_lines": []}).encode())


def test_parse_allocation_result_rejects_non_uuid_order_id() -> None:
    with pytest.raises(ValueError):
        parse_allocation_result(json.dumps({"order_id": "not-a-uuid"}).encode())


def test_parse_allocation_result_rejects_invalid_json() -> None:
    with pytest.raises(ValueError):
        parse_allocation_result(b"not-json")


def test_parse_allocation_result_rejects_non_object_payload() -> None:
    with pytest.raises(ValueError):
        parse_allocation_result(json.dumps([1]).encode())
