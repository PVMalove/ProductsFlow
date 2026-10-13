"""Чистые функции парсинга фактов payment-service (issue #375, D7; issue
#376, D7; issue #377, D7): `order_id` берётся из `correlation_id`; исход
авторизации — из типа события; `payment.captured.v1` несёт ещё
`causation_id`; `payment.voided.v1` только подтверждается."""

import json
import uuid

import pytest

from api.workers.commands.payment_event_handler import (
    PAYMENT_EVENT_TYPES,
    parse_authorization_result,
    parse_capture_result,
    parse_voided_order_id,
)
from domain.entities.order import AuthorizationOutcome


def _body(*, order_id: uuid.UUID, authorization_id: uuid.UUID) -> bytes:
    return json.dumps(
        {
            "authorization_id": str(authorization_id),
            "correlation_id": str(order_id),
            "causation_id": str(uuid.uuid4()),
        }
    ).encode()


@pytest.mark.parametrize(
    ("event_type", "outcome"),
    [
        ("payment.authorized.v1", AuthorizationOutcome.AUTHORIZED),
        ("payment.authorization_declined.v1", AuthorizationOutcome.DECLINED),
        ("payment.authorization_timed_out.v1", AuthorizationOutcome.TIMED_OUT),
    ],
)
def test_parse_maps_event_type_to_outcome_and_correlation_id_to_order_id(
    event_type: str, outcome: AuthorizationOutcome
) -> None:
    order_id = uuid.uuid4()
    authorization_id = uuid.uuid4()

    command = parse_authorization_result(
        event_type, _body(order_id=order_id, authorization_id=authorization_id)
    )

    assert command.order_id == order_id
    assert command.authorization_id == authorization_id
    assert command.outcome is outcome


def test_parse_rejects_unsupported_event_type() -> None:
    with pytest.raises(ValueError):
        parse_authorization_result(
            "payment.captured.v1",
            _body(order_id=uuid.uuid4(), authorization_id=uuid.uuid4()),
        )


def test_parse_rejects_missing_correlation_id() -> None:
    body = json.dumps({"authorization_id": str(uuid.uuid4())}).encode()

    with pytest.raises(ValueError):
        parse_authorization_result("payment.authorized.v1", body)


def test_parse_rejects_non_uuid_authorization_id() -> None:
    body = json.dumps(
        {"authorization_id": "not-a-uuid", "correlation_id": str(uuid.uuid4())}
    ).encode()

    with pytest.raises(ValueError):
        parse_authorization_result("payment.authorized.v1", body)


def test_parse_rejects_invalid_json() -> None:
    with pytest.raises(ValueError):
        parse_authorization_result("payment.authorized.v1", b"not-json")


def test_parse_rejects_non_object_payload() -> None:
    with pytest.raises(ValueError):
        parse_authorization_result("payment.authorized.v1", json.dumps([1]).encode())


def test_parse_capture_result_maps_authorization_correlation_causation() -> None:
    order_id = uuid.uuid4()
    authorization_id = uuid.uuid4()
    causation_id = uuid.uuid4()
    body = json.dumps(
        {
            "authorization_id": str(authorization_id),
            "correlation_id": str(order_id),
            "causation_id": str(causation_id),
        }
    ).encode()

    command = parse_capture_result(body)

    assert command.order_id == order_id
    assert command.authorization_id == authorization_id
    assert command.causation_id == causation_id


def test_parse_capture_result_rejects_missing_causation_id() -> None:
    body = json.dumps(
        {"authorization_id": str(uuid.uuid4()), "correlation_id": str(uuid.uuid4())}
    ).encode()

    with pytest.raises(ValueError):
        parse_capture_result(body)


def test_parse_capture_result_rejects_missing_authorization_id() -> None:
    body = json.dumps(
        {"correlation_id": str(uuid.uuid4()), "causation_id": str(uuid.uuid4())}
    ).encode()

    with pytest.raises(ValueError):
        parse_capture_result(body)


def test_parse_capture_result_rejects_non_uuid_correlation_id() -> None:
    body = json.dumps(
        {
            "authorization_id": str(uuid.uuid4()),
            "correlation_id": "not-a-uuid",
            "causation_id": str(uuid.uuid4()),
        }
    ).encode()

    with pytest.raises(ValueError):
        parse_capture_result(body)


def test_parse_capture_result_rejects_invalid_json() -> None:
    with pytest.raises(ValueError):
        parse_capture_result(b"not-json")


def test_parse_capture_result_rejects_non_object_payload() -> None:
    with pytest.raises(ValueError):
        parse_capture_result(json.dumps([1]).encode())


def test_voided_fact_is_bound_to_the_payment_queue() -> None:
    assert "payment.voided.v1" in PAYMENT_EVENT_TYPES


def test_parse_voided_maps_correlation_id_to_order_id() -> None:
    order_id = uuid.uuid4()

    parsed = parse_voided_order_id(
        _body(order_id=order_id, authorization_id=uuid.uuid4())
    )

    assert parsed == order_id


@pytest.mark.parametrize(
    "body",
    [
        json.dumps({"authorization_id": str(uuid.uuid4())}).encode(),
        json.dumps({"correlation_id": "not-a-uuid"}).encode(),
        b"not-json",
        json.dumps([1]).encode(),
    ],
    ids=["missing_correlation_id", "non_uuid_correlation_id", "invalid_json", "array"],
)
def test_parse_voided_rejects_a_bad_payload(body: bytes) -> None:
    with pytest.raises(ValueError):
        parse_voided_order_id(body)
