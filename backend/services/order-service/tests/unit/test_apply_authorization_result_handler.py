"""ApplyAuthorizationResultCommandHandler (issue #375, D6/AC2; issue #376,
D4/AC1) — фейковые repo: успех продолжает Saga к allocation с одним
intent'ом `inventory.allocate.v1`, отказ/таймаут переводит Order в
компенсируемый терминал с одним intent'ом `inventory.release.v1` (без
allocate); повторный результат — no-op без второго release/allocate."""

import uuid

import pytest

from application.commands.apply_authorization_result import (
    ApplyAuthorizationResultCommand,
    ApplyAuthorizationResultCommandHandler,
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
    FakeSagaCommandOutboxRepository,
)


def _order_awaiting_authorization() -> Order:
    line = OrderLine(
        id=uuid.uuid4(), product_id=uuid.uuid4(), quantity=1, unit_price_kopecks=100
    )
    order = Order.create(uuid.uuid4(), user_id=uuid.uuid4(), lines=[line])
    order.apply_reservation_result(confirmed_product_ids=frozenset({line.product_id}))
    return order


def _command(
    order_id: uuid.UUID, outcome: AuthorizationOutcome
) -> ApplyAuthorizationResultCommand:
    return ApplyAuthorizationResultCommand(
        order_id=order_id, authorization_id=uuid.uuid4(), outcome=outcome
    )


async def test_unknown_order_is_a_no_op() -> None:
    order_repo = FakeOrderRepository()
    outbox = FakeSagaCommandOutboxRepository()
    handler = ApplyAuthorizationResultCommandHandler(order_repo, outbox)

    await handler.execute(_command(uuid.uuid4(), AuthorizationOutcome.DECLINED))

    assert order_repo.save_calls == []
    assert outbox.release_intents == []


async def test_authorized_moves_to_allocation_and_requests_one_allocation() -> None:
    order = _order_awaiting_authorization()
    order_repo = FakeOrderRepository([order])
    outbox = FakeSagaCommandOutboxRepository()
    handler = ApplyAuthorizationResultCommandHandler(order_repo, outbox)
    command = _command(order.id, AuthorizationOutcome.AUTHORIZED)

    await handler.execute(command)

    saved = await order_repo.get_by_id(order.id)
    assert saved is not None
    assert saved.status is OrderStatus.PENDING
    assert saved.saga_step is OrderSagaStep.AWAITING_ALLOCATION
    assert saved.payment_authorization_id == command.authorization_id
    assert len(order_repo.save_calls) == 1
    assert outbox.allocation_intents == [order.id]
    assert outbox.release_intents == []
    assert outbox.authorization_intents == []
    assert outbox.capture_intents == []


async def test_repeated_authorized_result_requests_no_second_allocation() -> None:
    order = _order_awaiting_authorization()
    order_repo = FakeOrderRepository([order])
    outbox = FakeSagaCommandOutboxRepository()
    handler = ApplyAuthorizationResultCommandHandler(order_repo, outbox)
    await handler.execute(_command(order.id, AuthorizationOutcome.AUTHORIZED))

    await handler.execute(_command(order.id, AuthorizationOutcome.AUTHORIZED))

    assert outbox.allocation_intents == [order.id]
    assert len(order_repo.save_calls) == 1


@pytest.mark.parametrize(
    ("outcome", "failure_reason"),
    [
        (AuthorizationOutcome.DECLINED, "PAYMENT_DECLINED"),
        (AuthorizationOutcome.TIMED_OUT, "PAYMENT_TIMED_OUT"),
    ],
)
async def test_decline_or_timeout_fails_order_and_requests_release(
    outcome: AuthorizationOutcome, failure_reason: str
) -> None:
    order = _order_awaiting_authorization()
    order_repo = FakeOrderRepository([order])
    outbox = FakeSagaCommandOutboxRepository()
    handler = ApplyAuthorizationResultCommandHandler(order_repo, outbox)

    await handler.execute(_command(order.id, outcome))

    saved = await order_repo.get_by_id(order.id)
    assert saved is not None
    assert saved.status is OrderStatus.FAILED
    assert saved.failure_reason == failure_reason
    assert saved.saga_step is OrderSagaStep.COMPENSATING
    assert outbox.release_intents == [order.id]
    assert outbox.allocation_intents == []


async def test_repeated_result_is_a_no_op_without_a_second_release() -> None:
    order = _order_awaiting_authorization()
    order_repo = FakeOrderRepository([order])
    outbox = FakeSagaCommandOutboxRepository()
    handler = ApplyAuthorizationResultCommandHandler(order_repo, outbox)
    await handler.execute(_command(order.id, AuthorizationOutcome.DECLINED))

    # Тот же факт с другим message_id и противоречащий ему факт — оба no-op.
    await handler.execute(_command(order.id, AuthorizationOutcome.DECLINED))
    await handler.execute(_command(order.id, AuthorizationOutcome.AUTHORIZED))

    assert outbox.release_intents == [order.id]
    assert outbox.allocation_intents == []
    assert len(order_repo.save_calls) == 1
    saved = await order_repo.get_by_id(order.id)
    assert saved is not None
    assert saved.saga_step is OrderSagaStep.COMPENSATING
    assert saved.payment_authorization_id is None
