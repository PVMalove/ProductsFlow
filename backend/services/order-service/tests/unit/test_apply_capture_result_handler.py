"""ApplyCaptureResultCommandHandler (issue #376, D4/AC2) — фейковый repo:
`payment.captured.v1` в `AWAITING_CAPTURE` завершает Order (`COMPLETED`) и
сохраняет его с одним событием `OrderCompleted` (дренаж в outbox — забота
`OrderRepository.save`); повтор и capture не в своём шаге — no-op."""

import uuid

from application.commands.apply_capture_result import (
    ApplyCaptureResultCommand,
    ApplyCaptureResultCommandHandler,
)
from domain.entities.order import (
    AuthorizationOutcome,
    Order,
    OrderLine,
    OrderSagaStep,
    OrderStatus,
)
from domain.events.order_domain_event import OrderCompleted
from tests.unit.fake_order_repository import FakeOrderRepository


def _order_awaiting_allocation() -> Order:
    line = OrderLine(
        id=uuid.uuid4(), product_id=uuid.uuid4(), quantity=1, unit_price_kopecks=100
    )
    order = Order.create(uuid.uuid4(), user_id=uuid.uuid4(), lines=[line])
    order.apply_reservation_result(confirmed_product_ids=frozenset({line.product_id}))
    order.apply_authorization_result(
        outcome=AuthorizationOutcome.AUTHORIZED, authorization_id=uuid.uuid4()
    )
    return order


def _order_awaiting_capture() -> Order:
    order = _order_awaiting_allocation()
    order.apply_allocation_result()
    return order


def _command(order: Order) -> ApplyCaptureResultCommand:
    assert order.payment_authorization_id is not None
    return ApplyCaptureResultCommand(
        order_id=order.id,
        authorization_id=order.payment_authorization_id,
        causation_id=uuid.uuid4(),
    )


async def test_unknown_order_is_a_no_op() -> None:
    order_repo = FakeOrderRepository()
    handler = ApplyCaptureResultCommandHandler(order_repo)

    await handler.execute(_command(_order_awaiting_capture()))

    assert order_repo.save_calls == []


async def test_captured_completes_order_with_one_order_completed_event() -> None:
    order = _order_awaiting_capture()
    order_repo = FakeOrderRepository([order])
    handler = ApplyCaptureResultCommandHandler(order_repo)
    command = _command(order)

    await handler.execute(command)

    assert order_repo.save_calls == [order]
    saved = order_repo.save_calls[0]
    assert saved.status is OrderStatus.COMPLETED
    assert saved.saga_step is OrderSagaStep.CAPTURED
    events = saved.pull_events()
    assert len(events) == 1
    assert isinstance(events[0], OrderCompleted)
    assert events[0].causation_id == command.causation_id


async def test_repeated_captured_result_is_a_no_op() -> None:
    order = _order_awaiting_capture()
    order_repo = FakeOrderRepository([order])
    handler = ApplyCaptureResultCommandHandler(order_repo)
    await handler.execute(_command(order))
    order.pull_events()

    # Тот же факт с другим message_id — Saga уже в терминальном CAPTURED.
    await handler.execute(_command(order))

    assert len(order_repo.save_calls) == 1
    assert order.pull_events() == []


async def test_captured_result_before_allocation_is_a_no_op() -> None:
    order = _order_awaiting_allocation()
    order_repo = FakeOrderRepository([order])
    handler = ApplyCaptureResultCommandHandler(order_repo)

    await handler.execute(_command(order))

    assert order_repo.save_calls == []
    assert order.status is OrderStatus.PENDING
    assert order.saga_step is OrderSagaStep.AWAITING_ALLOCATION
    assert order.pull_events() == []


async def test_captured_result_for_another_authorization_is_a_no_op() -> None:
    order = _order_awaiting_capture()
    order_repo = FakeOrderRepository([order])
    handler = ApplyCaptureResultCommandHandler(order_repo)

    await handler.execute(
        ApplyCaptureResultCommand(
            order_id=order.id, authorization_id=uuid.uuid4(), causation_id=uuid.uuid4()
        )
    )

    assert order_repo.save_calls == []
    assert order.status is OrderStatus.PENDING
    assert order.saga_step is OrderSagaStep.AWAITING_CAPTURE
    assert order.pull_events() == []


async def test_capture_result_reads_the_order_under_a_row_lock() -> None:
    order = _order_awaiting_capture()
    order_repo = FakeOrderRepository([order])
    handler = ApplyCaptureResultCommandHandler(order_repo)

    await handler.execute(_command(order))

    assert order_repo.locked_reads == [order.id]
    assert order_repo.plain_reads == []
