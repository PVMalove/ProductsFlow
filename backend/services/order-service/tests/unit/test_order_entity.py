"""Domain-агрегат Order (issue #372, Seams for TDD #2, ADR 0016:7) —
внешний `OrderStatus` не раскрывает внутренний `OrderSagaStep` (D4);
`apply_reservation_result` реализует обе ветки D7 и no-op guard на повторную
доставку того же факта."""

import json
import uuid
from collections.abc import Callable
from datetime import UTC, datetime

import pytest

from domain.entities.order import (
    AuthorizationOutcome,
    Order,
    OrderLine,
    OrderSagaStep,
    OrderStatus,
)
from domain.events.order_domain_event import OrderCompleted

USER_ID = uuid.uuid4()


def _order_with_lines(count: int = 2) -> tuple[Order, list[OrderLine]]:
    lines = [
        OrderLine(
            id=uuid.uuid4(),
            product_id=uuid.uuid4(),
            quantity=1,
            unit_price_kopecks=10_000,
        )
        for _ in range(count)
    ]
    order = Order.create(uuid.uuid4(), user_id=USER_ID, lines=list(lines))
    return order, lines


def test_create_starts_pending_awaiting_reservation() -> None:
    order, lines = _order_with_lines()

    assert order.user_id == USER_ID
    assert order.status is OrderStatus.PENDING
    assert order.saga_step is OrderSagaStep.AWAITING_RESERVATION
    assert order.failure_reason is None
    assert order.lines == lines


def test_apply_reservation_result_zero_confirmed_marks_order_failed() -> None:
    order, _lines = _order_with_lines()

    applied = order.apply_reservation_result(confirmed_product_ids=frozenset())

    assert applied is True
    assert order.status is OrderStatus.FAILED
    assert order.saga_step is OrderSagaStep.RESERVATION_FAILED
    assert order.failure_reason == "NO_ITEMS_AVAILABLE"


def test_apply_reservation_result_zero_confirmed_keeps_lines_unchanged() -> None:
    order, lines = _order_with_lines()

    order.apply_reservation_result(confirmed_product_ids=frozenset())

    assert order.lines == lines


def test_apply_reservation_result_partial_confirmed_trims_lines() -> None:
    order, lines = _order_with_lines(2)
    confirmed_product_id = lines[0].product_id

    applied = order.apply_reservation_result(
        confirmed_product_ids=frozenset({confirmed_product_id})
    )

    assert applied is True
    assert order.status is OrderStatus.PENDING
    assert order.saga_step is OrderSagaStep.AWAITING_AUTHORIZATION
    assert order.failure_reason is None
    assert [line.product_id for line in order.lines] == [confirmed_product_id]


def test_apply_reservation_result_full_confirmed_keeps_all_lines() -> None:
    order, lines = _order_with_lines(2)
    all_product_ids = frozenset(line.product_id for line in lines)

    order.apply_reservation_result(confirmed_product_ids=all_product_ids)

    assert order.saga_step is OrderSagaStep.AWAITING_AUTHORIZATION
    assert len(order.lines) == 2


def test_authorization_amount_is_the_sum_of_confirmed_lines_only() -> None:
    confirmed = OrderLine(
        id=uuid.uuid4(), product_id=uuid.uuid4(), quantity=3, unit_price_kopecks=1_500
    )
    unavailable = OrderLine(
        id=uuid.uuid4(), product_id=uuid.uuid4(), quantity=2, unit_price_kopecks=7_000
    )
    order = Order.create(uuid.uuid4(), user_id=USER_ID, lines=[confirmed, unavailable])

    order.apply_reservation_result(
        confirmed_product_ids=frozenset({confirmed.product_id})
    )

    assert order.authorization_amount_kopecks() == 3 * 1_500


def test_create_has_no_payment_authorization_id() -> None:
    order, _lines = _order_with_lines()

    assert order.payment_authorization_id is None


def test_apply_reservation_result_is_a_no_op_once_already_resolved() -> None:
    order, lines = _order_with_lines(2)
    confirmed_product_id = lines[0].product_id
    order.apply_reservation_result(
        confirmed_product_ids=frozenset({confirmed_product_id})
    )

    # Повторная доставка того же факта (broker redelivery) — no-op.
    applied_again = order.apply_reservation_result(confirmed_product_ids=frozenset())

    assert applied_again is False
    assert order.saga_step is OrderSagaStep.AWAITING_AUTHORIZATION
    assert [line.product_id for line in order.lines] == [confirmed_product_id]


def test_reconstitute_preserves_all_fields() -> None:
    order_id = uuid.uuid4()
    created_at = datetime.now(UTC)
    line = OrderLine(
        id=uuid.uuid4(), product_id=uuid.uuid4(), quantity=3, unit_price_kopecks=500
    )

    order = Order.reconstitute(
        order_id,
        user_id=USER_ID,
        status=OrderStatus.FAILED,
        saga_step=OrderSagaStep.RESERVATION_FAILED,
        lines=[line],
        failure_reason="NO_ITEMS_AVAILABLE",
        created_at=created_at,
    )

    assert order.id == order_id
    assert order.status is OrderStatus.FAILED
    assert order.saga_step is OrderSagaStep.RESERVATION_FAILED
    assert order.lines == [line]
    assert order.failure_reason == "NO_ITEMS_AVAILABLE"
    assert order.created_at == created_at
    assert order.payment_authorization_id is None


def _order_awaiting_authorization() -> Order:
    order, lines = _order_with_lines(2)
    order.apply_reservation_result(
        confirmed_product_ids=frozenset({lines[0].product_id})
    )
    return order


def test_authorized_moves_saga_to_allocation_and_stores_authorization_id() -> None:
    order = _order_awaiting_authorization()
    authorization_id = uuid.uuid4()

    applied = order.apply_authorization_result(
        outcome=AuthorizationOutcome.AUTHORIZED, authorization_id=authorization_id
    )

    assert applied is True
    assert order.status is OrderStatus.PENDING
    assert order.saga_step is OrderSagaStep.AWAITING_ALLOCATION
    assert order.payment_authorization_id == authorization_id
    assert order.failure_reason is None


@pytest.mark.parametrize(
    ("outcome", "failure_reason"),
    [
        (AuthorizationOutcome.DECLINED, "PAYMENT_DECLINED"),
        (AuthorizationOutcome.TIMED_OUT, "PAYMENT_TIMED_OUT"),
    ],
)
def test_declined_or_timed_out_fails_order_and_starts_compensation(
    outcome: AuthorizationOutcome, failure_reason: str
) -> None:
    order = _order_awaiting_authorization()
    lines_before = list(order.lines)

    applied = order.apply_authorization_result(
        outcome=outcome, authorization_id=uuid.uuid4()
    )

    assert applied is True
    assert order.status is OrderStatus.FAILED
    assert order.failure_reason == failure_reason
    assert order.saga_step is OrderSagaStep.COMPENSATING
    assert order.payment_authorization_id is None
    assert order.lines == lines_before


def test_repeated_authorization_result_is_a_no_op() -> None:
    order = _order_awaiting_authorization()
    authorization_id = uuid.uuid4()
    order.apply_authorization_result(
        outcome=AuthorizationOutcome.AUTHORIZED, authorization_id=authorization_id
    )

    # Повторная доставка с ДРУГИМ исходом — Saga уже покинула шаг.
    applied_again = order.apply_authorization_result(
        outcome=AuthorizationOutcome.DECLINED, authorization_id=uuid.uuid4()
    )

    assert applied_again is False
    assert order.status is OrderStatus.PENDING
    assert order.saga_step is OrderSagaStep.AWAITING_ALLOCATION
    assert order.payment_authorization_id == authorization_id


def test_authorization_result_before_reservation_is_a_no_op() -> None:
    order, _lines = _order_with_lines()

    applied = order.apply_authorization_result(
        outcome=AuthorizationOutcome.DECLINED, authorization_id=uuid.uuid4()
    )

    assert applied is False
    assert order.status is OrderStatus.PENDING
    assert order.saga_step is OrderSagaStep.AWAITING_RESERVATION


def _order_compensating() -> Order:
    order = _order_awaiting_authorization()
    order.apply_authorization_result(
        outcome=AuthorizationOutcome.DECLINED, authorization_id=uuid.uuid4()
    )
    return order


def test_complete_compensation_keeps_failed_order_with_its_lines() -> None:
    order = _order_compensating()
    lines_before = list(order.lines)

    completed = order.complete_compensation()

    assert completed is True
    assert order.saga_step is OrderSagaStep.COMPENSATED
    assert order.status is OrderStatus.FAILED
    assert order.failure_reason == "PAYMENT_DECLINED"
    assert order.lines == lines_before


def test_repeated_compensation_is_a_no_op() -> None:
    order = _order_compensating()
    order.complete_compensation()

    assert order.complete_compensation() is False
    assert order.saga_step is OrderSagaStep.COMPENSATED


def test_compensation_outside_compensating_step_is_a_no_op() -> None:
    order = _order_awaiting_authorization()

    completed = order.complete_compensation()

    assert completed is False
    assert order.status is OrderStatus.PENDING
    assert order.saga_step is OrderSagaStep.AWAITING_AUTHORIZATION


def _order_awaiting_allocation() -> Order:
    order = _order_awaiting_authorization()
    order.apply_authorization_result(
        outcome=AuthorizationOutcome.AUTHORIZED, authorization_id=uuid.uuid4()
    )
    return order


def test_allocation_result_moves_saga_to_capture_and_keeps_order_pending() -> None:
    order = _order_awaiting_allocation()
    authorization_id = order.payment_authorization_id

    applied = order.apply_allocation_result()

    assert applied is True
    assert order.status is OrderStatus.PENDING
    assert order.saga_step is OrderSagaStep.AWAITING_CAPTURE
    assert order.payment_authorization_id == authorization_id
    assert order.failure_reason is None


def test_repeated_allocation_result_is_a_no_op() -> None:
    order = _order_awaiting_allocation()
    order.apply_allocation_result()

    assert order.apply_allocation_result() is False
    assert order.saga_step is OrderSagaStep.AWAITING_CAPTURE


@pytest.mark.parametrize(
    "order_factory",
    [
        lambda: _order_with_lines()[0],
        _order_awaiting_authorization,
        _order_compensating,
    ],
    ids=["awaiting_reservation", "awaiting_authorization", "compensating"],
)
def test_allocation_result_outside_awaiting_allocation_is_a_no_op(
    order_factory: Callable[[], Order],
) -> None:
    order = order_factory()
    status_before = order.status
    step_before = order.saga_step

    applied = order.apply_allocation_result()

    assert applied is False
    assert order.status is status_before
    assert order.saga_step is step_before


def _order_awaiting_capture() -> Order:
    order = _order_awaiting_allocation()
    order.apply_allocation_result()
    return order


def _authorization_id(order: Order) -> uuid.UUID:
    assert order.payment_authorization_id is not None
    return order.payment_authorization_id


def test_capture_result_completes_order_and_records_order_completed() -> None:
    order = _order_awaiting_capture()
    causation_id = uuid.uuid4()

    applied = order.apply_capture_result(
        authorization_id=_authorization_id(order), causation_id=causation_id
    )

    assert applied is True
    assert order.status is OrderStatus.COMPLETED
    assert order.saga_step is OrderSagaStep.CAPTURED
    assert order.failure_reason is None
    events = order.pull_events()
    assert len(events) == 1
    event = events[0]
    assert isinstance(event, OrderCompleted)
    assert event.event_type == "order.completed.v1"
    assert event.aggregate_type == "Order"
    assert event.aggregate_id() == order.id
    assert event.to_payload() == {
        "order_id": str(order.id),
        "correlation_id": str(order.id),
        "causation_id": str(causation_id),
    }
    assert str(order.user_id) not in json.dumps(event.to_payload())


def test_repeated_capture_result_is_a_no_op_without_a_second_event() -> None:
    order = _order_awaiting_capture()
    authorization_id = _authorization_id(order)
    order.apply_capture_result(
        authorization_id=authorization_id, causation_id=uuid.uuid4()
    )
    order.pull_events()

    applied_again = order.apply_capture_result(
        authorization_id=authorization_id, causation_id=uuid.uuid4()
    )

    assert applied_again is False
    assert order.status is OrderStatus.COMPLETED
    assert order.saga_step is OrderSagaStep.CAPTURED
    assert order.pull_events() == []


def test_capture_result_for_another_authorization_is_a_no_op() -> None:
    order = _order_awaiting_capture()

    applied = order.apply_capture_result(
        authorization_id=uuid.uuid4(), causation_id=uuid.uuid4()
    )

    assert applied is False
    assert order.status is OrderStatus.PENDING
    assert order.saga_step is OrderSagaStep.AWAITING_CAPTURE
    assert order.pull_events() == []


@pytest.mark.parametrize(
    "order_factory",
    [
        _order_awaiting_authorization,
        _order_awaiting_allocation,
        _order_compensating,
    ],
    ids=["awaiting_authorization", "awaiting_allocation", "compensating"],
)
def test_capture_result_outside_awaiting_capture_is_a_no_op(
    order_factory: Callable[[], Order],
) -> None:
    order = order_factory()
    status_before = order.status
    step_before = order.saga_step

    applied = order.apply_capture_result(
        authorization_id=uuid.uuid4(), causation_id=uuid.uuid4()
    )

    assert applied is False
    assert order.status is status_before
    assert order.saga_step is step_before
    assert order.pull_events() == []


def test_allocation_result_after_capture_is_a_no_op() -> None:
    order = _order_awaiting_capture()
    order.apply_capture_result(
        authorization_id=_authorization_id(order), causation_id=uuid.uuid4()
    )

    assert order.apply_allocation_result() is False
    assert order.status is OrderStatus.COMPLETED
    assert order.saga_step is OrderSagaStep.CAPTURED


# --- issue #377: отмена владельцем до capture -------------------------------


def _order_compensated() -> Order:
    order = _order_compensating()
    order.complete_compensation()
    return order


def _order_reservation_failed() -> Order:
    order, _lines = _order_with_lines()
    order.apply_reservation_result(confirmed_product_ids=frozenset())
    return order


def _order_captured() -> Order:
    order = _order_awaiting_capture()
    order.apply_capture_result(
        authorization_id=_authorization_id(order), causation_id=uuid.uuid4()
    )
    order.pull_events()
    return order


def _order_cancelled_awaiting_reservation() -> Order:
    order, _lines = _order_with_lines()
    order.cancel()
    return order


def _order_expired_awaiting_reservation() -> Order:
    order, lines = _order_with_lines()
    return Order.reconstitute(
        order.id,
        user_id=order.user_id,
        status=OrderStatus.EXPIRED,
        saga_step=OrderSagaStep.AWAITING_RESERVATION,
        lines=lines,
        failure_reason="RESERVATION_EXPIRED",
        created_at=order.created_at,
    )


@pytest.mark.parametrize(
    ("order_factory", "saga_step_after"),
    [
        (lambda: _order_with_lines()[0], OrderSagaStep.AWAITING_RESERVATION),
        (_order_awaiting_authorization, OrderSagaStep.COMPENSATING),
        (_order_awaiting_allocation, OrderSagaStep.COMPENSATING),
    ],
    ids=["awaiting_reservation", "awaiting_authorization", "awaiting_allocation"],
)
def test_cancel_before_capture_cancels_the_order(
    order_factory: Callable[[], Order], saga_step_after: OrderSagaStep
) -> None:
    order = order_factory()
    lines_before = list(order.lines)
    authorization_before = order.payment_authorization_id

    cancelled = order.cancel()

    assert cancelled is True
    assert order.status is OrderStatus.CANCELLED
    assert order.failure_reason == "CANCELLED_BY_CUSTOMER"
    # В AWAITING_RESERVATION шаг сохраняется: компенсацию решит результат
    # резерва в пути.
    assert order.saga_step is saga_step_after
    assert order.lines == lines_before
    assert order.payment_authorization_id == authorization_before


@pytest.mark.parametrize(
    "order_factory",
    [
        _order_awaiting_capture,
        _order_captured,
        _order_compensating,
        _order_compensated,
        _order_reservation_failed,
        _order_cancelled_awaiting_reservation,
        _order_expired_awaiting_reservation,
    ],
    ids=[
        "awaiting_capture",
        "captured",
        "compensating",
        "compensated",
        "reservation_failed",
        "already_cancelled",
        "expired",
    ],
)
def test_cancel_outside_pending_before_capture_is_a_no_op(
    order_factory: Callable[[], Order],
) -> None:
    order = order_factory()
    status_before = order.status
    step_before = order.saga_step
    reason_before = order.failure_reason

    cancelled = order.cancel()

    assert cancelled is False
    assert order.status is status_before
    assert order.saga_step is step_before
    assert order.failure_reason == reason_before


def test_reservation_result_after_cancel_compensates_the_confirmed_lines() -> None:
    order, lines = _order_with_lines(2)
    order.cancel()

    applied = order.apply_reservation_result(
        confirmed_product_ids=frozenset({lines[0].product_id})
    )

    assert applied is True
    assert order.status is OrderStatus.CANCELLED
    assert order.failure_reason == "CANCELLED_BY_CUSTOMER"
    assert order.saga_step is OrderSagaStep.COMPENSATING
    assert order.lines == [lines[0]]


def test_empty_reservation_result_after_cancel_completes_compensation() -> None:
    order, lines = _order_with_lines(2)
    order.cancel()

    applied = order.apply_reservation_result(confirmed_product_ids=frozenset())

    assert applied is True
    assert order.status is OrderStatus.CANCELLED
    assert order.failure_reason == "CANCELLED_BY_CUSTOMER"
    assert order.saga_step is OrderSagaStep.COMPENSATED
    assert order.lines == lines


def test_reservation_result_after_expiry_completes_compensation() -> None:
    order = _order_expired_awaiting_reservation()
    lines_before = list(order.lines)

    applied = order.apply_reservation_result(
        confirmed_product_ids=frozenset({lines_before[0].product_id})
    )

    assert applied is True
    assert order.status is OrderStatus.EXPIRED
    assert order.saga_step is OrderSagaStep.COMPENSATED
    assert order.lines == lines_before


def test_repeated_reservation_result_after_cancel_is_a_no_op() -> None:
    order, lines = _order_with_lines(2)
    order.cancel()
    order.apply_reservation_result(
        confirmed_product_ids=frozenset({lines[0].product_id})
    )

    applied_again = order.apply_reservation_result(confirmed_product_ids=frozenset())

    assert applied_again is False
    assert order.saga_step is OrderSagaStep.COMPENSATING
    assert order.lines == [lines[0]]


def test_compensation_after_cancel_keeps_the_cancelled_order() -> None:
    order = _order_awaiting_authorization()
    order.cancel()

    assert order.complete_compensation() is True
    assert order.status is OrderStatus.CANCELLED
    assert order.failure_reason == "CANCELLED_BY_CUSTOMER"
    assert order.saga_step is OrderSagaStep.COMPENSATED


def test_authorization_result_after_cancel_does_not_advance_the_saga() -> None:
    order = _order_awaiting_authorization()
    order.cancel()

    applied = order.apply_authorization_result(
        outcome=AuthorizationOutcome.AUTHORIZED, authorization_id=uuid.uuid4()
    )

    assert applied is False
    assert order.status is OrderStatus.CANCELLED
    assert order.saga_step is OrderSagaStep.COMPENSATING
    assert order.payment_authorization_id is None


def test_allocation_result_after_cancel_requests_no_capture() -> None:
    order = _order_awaiting_allocation()
    order.cancel()

    assert order.apply_allocation_result() is False
    assert order.saga_step is OrderSagaStep.COMPENSATING


@pytest.mark.parametrize(
    "order_factory",
    [
        _order_cancelled_awaiting_reservation,
        _order_expired_awaiting_reservation,
    ],
    ids=["cancelled", "expired"],
)
def test_late_authorization_of_a_cancelled_or_expired_order_is_recorded_once(
    order_factory: Callable[[], Order],
) -> None:
    order = order_factory()
    status_before = order.status
    step_before = order.saga_step
    authorization_id = uuid.uuid4()

    recorded = order.record_late_authorization(authorization_id=authorization_id)
    recorded_again = order.record_late_authorization(authorization_id=uuid.uuid4())

    assert recorded is True
    assert recorded_again is False
    assert order.payment_authorization_id == authorization_id
    assert order.status is status_before
    assert order.saga_step is step_before


def test_late_authorization_is_not_recorded_over_a_stored_authorization() -> None:
    order = _order_awaiting_allocation()
    stored = order.payment_authorization_id
    order.cancel()

    assert order.record_late_authorization(authorization_id=uuid.uuid4()) is False
    assert order.payment_authorization_id == stored


@pytest.mark.parametrize(
    "order_factory",
    [
        _order_awaiting_authorization,
        _order_compensating,
        _order_reservation_failed,
    ],
    ids=["pending", "failed_compensating", "reservation_failed"],
)
def test_late_authorization_outside_cancelled_or_expired_is_a_no_op(
    order_factory: Callable[[], Order],
) -> None:
    order = order_factory()

    assert order.record_late_authorization(authorization_id=uuid.uuid4()) is False
    assert order.payment_authorization_id is None
