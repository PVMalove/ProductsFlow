"""Domain-агрегат Order (issue #372, Seams for TDD #2, ADR 0016:7) —
внешний `OrderStatus` не раскрывает внутренний `OrderSagaStep` (D4);
`apply_reservation_result` реализует обе ветки D7 и no-op guard на повторную
доставку того же факта."""

import uuid
from datetime import UTC, datetime

from domain.entities.order import Order, OrderLine, OrderSagaStep, OrderStatus

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
    assert order.saga_step is OrderSagaStep.RESERVATION_CONFIRMED
    assert order.failure_reason is None
    assert [line.product_id for line in order.lines] == [confirmed_product_id]


def test_apply_reservation_result_full_confirmed_keeps_all_lines() -> None:
    order, lines = _order_with_lines(2)
    all_product_ids = frozenset(line.product_id for line in lines)

    order.apply_reservation_result(confirmed_product_ids=all_product_ids)

    assert order.saga_step is OrderSagaStep.RESERVATION_CONFIRMED
    assert len(order.lines) == 2


def test_apply_reservation_result_is_a_no_op_once_already_resolved() -> None:
    order, lines = _order_with_lines(2)
    confirmed_product_id = lines[0].product_id
    order.apply_reservation_result(
        confirmed_product_ids=frozenset({confirmed_product_id})
    )

    # Повторная доставка того же факта (broker redelivery) — no-op.
    applied_again = order.apply_reservation_result(confirmed_product_ids=frozenset())

    assert applied_again is False
    assert order.saga_step is OrderSagaStep.RESERVATION_CONFIRMED
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
