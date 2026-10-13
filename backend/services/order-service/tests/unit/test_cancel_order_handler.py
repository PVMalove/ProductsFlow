"""CancelOrderCommandHandler (issue #377, D4/D5) — фейковый UoW+repo: отмена
в каждом шаге до capture ставит intents компенсации по матрице брифа и
коммитит; чужой/неизвестный Order — 403/404 до мутации; не отменяемый Order
— 409-эквивалент без сохранения и команд; повтор отмены — успех без новых
intent'ов."""

import uuid
from collections.abc import Callable

import pytest
from kernel_domain.errors import ErrorType
from kernel_platform.security import Actor, ActorRole

from application.commands.cancel_order import (
    CancelOrderCommand,
    CancelOrderCommandHandler,
)
from domain.entities.order import (
    Order,
    OrderSagaStep,
)
from tests.unit.fake_order_cancellation_unit_of_work import (
    FakeOrderCancellationUnitOfWork,
)
from tests.unit.fake_order_repository import FakeOrderRepository
from tests.unit.fake_saga_command_outbox_repository import (
    FakeSagaCommandOutboxRepository,
    VoidIntent,
)
from tests.unit.order_builders import (
    order_awaiting_allocation,
    order_awaiting_authorization,
    order_awaiting_capture,
    order_awaiting_reservation,
    order_compensating,
)

ACTOR = Actor(id=uuid.uuid4(), role=ActorRole.USER)
AUTHORIZATION_ID = uuid.uuid4()


def _order_awaiting_reservation() -> Order:
    return order_awaiting_reservation(user_id=ACTOR.id)


def _order_awaiting_authorization() -> Order:
    return order_awaiting_authorization(user_id=ACTOR.id)


def _order_awaiting_allocation() -> Order:
    return order_awaiting_allocation(
        user_id=ACTOR.id, authorization_id=AUTHORIZATION_ID
    )


def _order_awaiting_capture() -> Order:
    return order_awaiting_capture(user_id=ACTOR.id, authorization_id=AUTHORIZATION_ID)


def _order_failed_compensating() -> Order:
    return order_compensating(user_id=ACTOR.id)


def _order_reservation_failed() -> Order:
    order = _order_awaiting_reservation()
    order.apply_reservation_result(confirmed_product_ids=frozenset())
    return order


def _handler(
    orders: list[Order],
) -> tuple[CancelOrderCommandHandler, FakeOrderCancellationUnitOfWork]:
    uow = FakeOrderCancellationUnitOfWork(
        orders=FakeOrderRepository(orders),
        saga_command_outbox=FakeSagaCommandOutboxRepository(),
    )
    return CancelOrderCommandHandler(uow), uow


@pytest.mark.parametrize(
    ("order_factory", "saga_step", "releases", "voids"),
    [
        (_order_awaiting_reservation, OrderSagaStep.AWAITING_RESERVATION, 0, 0),
        (_order_awaiting_authorization, OrderSagaStep.COMPENSATING, 1, 0),
        (_order_awaiting_allocation, OrderSagaStep.COMPENSATING, 1, 1),
    ],
    ids=["awaiting_reservation", "awaiting_authorization", "awaiting_allocation"],
)
async def test_cancel_before_capture_cancels_and_enqueues_compensation(
    order_factory: Callable[[], Order],
    saga_step: OrderSagaStep,
    releases: int,
    voids: int,
) -> None:
    order = order_factory()
    handler, uow = _handler([order])

    result = await handler.execute(CancelOrderCommand(actor=ACTOR, order_id=order.id))

    assert result.is_ok
    assert result.value.status == "cancelled"
    assert result.value.failure_reason == "CANCELLED_BY_CUSTOMER"
    assert uow.committed is True
    assert uow.orders.save_calls == [order]
    assert order.saga_step is saga_step
    assert uow.saga_command_outbox.release_intents == [order.id] * releases
    assert (
        uow.saga_command_outbox.void_intents
        == [VoidIntent(order_id=order.id, authorization_id=AUTHORIZATION_ID)] * voids
    )


async def test_unknown_order_is_not_found() -> None:
    handler, uow = _handler([])

    result = await handler.execute(
        CancelOrderCommand(actor=ACTOR, order_id=uuid.uuid4())
    )

    assert result.is_err
    assert result.error.code == "order_not_found"
    assert result.error.type is ErrorType.NOT_FOUND
    assert uow.committed is False


async def test_foreign_order_is_denied_and_left_unchanged() -> None:
    order = _order_awaiting_authorization()
    handler, uow = _handler([order])
    stranger = Actor(id=uuid.uuid4(), role=ActorRole.USER)

    result = await handler.execute(
        CancelOrderCommand(actor=stranger, order_id=order.id)
    )

    assert result.is_err
    assert result.error.code == "order_access_denied"
    assert result.error.type is ErrorType.FORBIDDEN
    assert uow.committed is False
    assert uow.orders.save_calls == []
    assert order.saga_step is OrderSagaStep.AWAITING_AUTHORIZATION


@pytest.mark.parametrize(
    "order_factory",
    [_order_awaiting_capture, _order_failed_compensating, _order_reservation_failed],
    ids=["awaiting_capture", "failed_compensating", "reservation_failed"],
)
async def test_order_not_cancellable_conflicts_without_changes(
    order_factory: Callable[[], Order],
) -> None:
    order = order_factory()
    status_before = order.status
    step_before = order.saga_step
    handler, uow = _handler([order])

    result = await handler.execute(CancelOrderCommand(actor=ACTOR, order_id=order.id))

    assert result.is_err
    assert result.error.code == "order_not_cancellable"
    assert uow.committed is False
    assert uow.orders.save_calls == []
    assert uow.saga_command_outbox.release_intents == []
    assert uow.saga_command_outbox.void_intents == []
    assert order.status is status_before
    assert order.saga_step is step_before


async def test_repeated_cancel_succeeds_without_new_commands() -> None:
    order = _order_awaiting_allocation()
    handler, uow = _handler([order])
    await handler.execute(CancelOrderCommand(actor=ACTOR, order_id=order.id))

    result = await handler.execute(CancelOrderCommand(actor=ACTOR, order_id=order.id))

    assert result.is_ok
    assert result.value.status == "cancelled"
    assert len(uow.orders.save_calls) == 1
    assert uow.saga_command_outbox.release_intents == [order.id]
    assert len(uow.saga_command_outbox.void_intents) == 1


async def test_cancel_reads_the_order_under_a_row_lock() -> None:
    order = _order_awaiting_authorization()
    handler, uow = _handler([order])

    await handler.execute(CancelOrderCommand(actor=ACTOR, order_id=order.id))

    assert uow.orders.locked_reads == [order.id]
    assert uow.orders.plain_reads == []
