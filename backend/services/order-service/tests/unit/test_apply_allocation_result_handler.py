"""ApplyAllocationResultCommandHandler (issue #376, D4/AC1) — фейковые repo:
`inventory.allocated.v1` в `AWAITING_ALLOCATION` переводит Saga к capture с
одним intent'ом `payment.capture.v1` на сохранённый `authorization_id`;
повтор и результат в другом шаге — no-op без команды."""

import uuid

from application.commands.apply_allocation_result import (
    ApplyAllocationResultCommand,
    ApplyAllocationResultCommandHandler,
)
from domain.entities.order import (
    AuthorizationOutcome,
    Order,
    OrderLine,
    OrderSagaStep,
    OrderStatus,
)
from tests.unit.fake_order_repository import FakeOrderRepository
from tests.unit.fake_saga_command_outbox_repository import (
    CaptureIntent,
    FakeSagaCommandOutboxRepository,
)


def _order_awaiting_authorization() -> Order:
    line = OrderLine(
        id=uuid.uuid4(), product_id=uuid.uuid4(), quantity=1, unit_price_kopecks=100
    )
    order = Order.create(uuid.uuid4(), user_id=uuid.uuid4(), lines=[line])
    order.apply_reservation_result(confirmed_product_ids=frozenset({line.product_id}))
    return order


def _order_awaiting_allocation(authorization_id: uuid.UUID) -> Order:
    order = _order_awaiting_authorization()
    order.apply_authorization_result(
        outcome=AuthorizationOutcome.AUTHORIZED, authorization_id=authorization_id
    )
    return order


async def test_unknown_order_is_a_no_op() -> None:
    order_repo = FakeOrderRepository()
    outbox = FakeSagaCommandOutboxRepository()
    handler = ApplyAllocationResultCommandHandler(order_repo, outbox)

    await handler.execute(ApplyAllocationResultCommand(order_id=uuid.uuid4()))

    assert order_repo.save_calls == []
    assert outbox.capture_intents == []


async def test_allocated_moves_to_capture_and_requests_capture() -> None:
    authorization_id = uuid.uuid4()
    order = _order_awaiting_allocation(authorization_id)
    order_repo = FakeOrderRepository([order])
    outbox = FakeSagaCommandOutboxRepository()
    handler = ApplyAllocationResultCommandHandler(order_repo, outbox)

    await handler.execute(ApplyAllocationResultCommand(order_id=order.id))

    saved = await order_repo.get_by_id(order.id)
    assert saved is not None
    assert saved.status is OrderStatus.PENDING
    assert saved.saga_step is OrderSagaStep.AWAITING_CAPTURE
    assert len(order_repo.save_calls) == 1
    assert outbox.capture_intents == [
        CaptureIntent(order_id=order.id, authorization_id=authorization_id)
    ]
    assert outbox.allocation_intents == []
    assert outbox.release_intents == []


async def test_repeated_allocated_result_requests_no_second_capture() -> None:
    order = _order_awaiting_allocation(uuid.uuid4())
    order_repo = FakeOrderRepository([order])
    outbox = FakeSagaCommandOutboxRepository()
    handler = ApplyAllocationResultCommandHandler(order_repo, outbox)
    await handler.execute(ApplyAllocationResultCommand(order_id=order.id))

    # Тот же факт с другим message_id — Saga уже покинула шаг.
    await handler.execute(ApplyAllocationResultCommand(order_id=order.id))

    assert len(outbox.capture_intents) == 1
    assert len(order_repo.save_calls) == 1


async def test_allocated_result_before_authorization_is_a_no_op() -> None:
    order = _order_awaiting_authorization()
    order_repo = FakeOrderRepository([order])
    outbox = FakeSagaCommandOutboxRepository()
    handler = ApplyAllocationResultCommandHandler(order_repo, outbox)

    await handler.execute(ApplyAllocationResultCommand(order_id=order.id))

    assert order.saga_step is OrderSagaStep.AWAITING_AUTHORIZATION
    assert order_repo.save_calls == []
    assert outbox.capture_intents == []
