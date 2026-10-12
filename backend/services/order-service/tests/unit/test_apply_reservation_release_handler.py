"""ApplyReservationReleaseCommandHandler (issue #375, D6/AC3) — фейковые
repo: `inventory.released.v1` в `COMPENSATING` завершает компенсацию и
возвращает строки Order в Cart с причиной результата; Order остаётся
`FAILED` в истории; повтор и release в другом шаге — no-op. issue #377:
`reason=expired` у незавершённого Order — `EXPIRED`, void сохранённой
авторизации и возврат строк; у отменённого — обычное завершение
компенсации."""

import uuid
from datetime import UTC, datetime

from application.commands.apply_reservation_release import (
    ApplyReservationReleaseCommand,
    ApplyReservationReleaseCommandHandler,
)
from domain.entities.cart import Cart
from domain.entities.order import (
    AuthorizationOutcome,
    Order,
    OrderLine,
    OrderSagaStep,
    OrderStatus,
)
from domain.value_objects.cart_id import CartId
from tests.unit.fake_cart_repository import FakeCartRepository
from tests.unit.fake_order_repository import FakeOrderRepository
from tests.unit.fake_saga_command_outbox_repository import (
    FakeSagaCommandOutboxRepository,
    VoidIntent,
)

USER_ID = uuid.uuid4()


def _order_awaiting_authorization(*, quantities: tuple[int, ...] = (2, 1)) -> Order:
    lines = [
        OrderLine(
            id=uuid.uuid4(),
            product_id=uuid.uuid4(),
            quantity=quantity,
            unit_price_kopecks=100,
        )
        for quantity in quantities
    ]
    order = Order.create(uuid.uuid4(), user_id=USER_ID, lines=lines)
    order.apply_reservation_result(
        confirmed_product_ids=frozenset(line.product_id for line in lines)
    )
    return order


def _handler(
    order_repo: FakeOrderRepository,
    cart_repo: FakeCartRepository,
    outbox: FakeSagaCommandOutboxRepository | None = None,
) -> ApplyReservationReleaseCommandHandler:
    return ApplyReservationReleaseCommandHandler(
        order_repo, cart_repo, outbox or FakeSagaCommandOutboxRepository()
    )


def _manual(order_id: uuid.UUID) -> ApplyReservationReleaseCommand:
    return ApplyReservationReleaseCommand(order_id=order_id, expired=False)


def _expired(order_id: uuid.UUID) -> ApplyReservationReleaseCommand:
    return ApplyReservationReleaseCommand(order_id=order_id, expired=True)


def _order_compensating(outcome: AuthorizationOutcome) -> Order:
    order = _order_awaiting_authorization()
    order.apply_authorization_result(outcome=outcome, authorization_id=uuid.uuid4())
    return order


async def test_unknown_order_is_a_no_op() -> None:
    order_repo = FakeOrderRepository()
    cart_repo = FakeCartRepository()
    handler = _handler(order_repo, cart_repo)

    await handler.execute(_manual(uuid.uuid4()))

    assert order_repo.save_calls == []
    assert cart_repo.save_calls == []


async def test_release_in_compensating_returns_lines_to_cart_with_reason() -> None:
    order = _order_compensating(AuthorizationOutcome.DECLINED)
    order_repo = FakeOrderRepository([order])
    cart_repo = FakeCartRepository()
    handler = _handler(order_repo, cart_repo)

    await handler.execute(_manual(order.id))

    saved_order = await order_repo.get_by_id(order.id)
    assert saved_order is not None
    assert saved_order.saga_step is OrderSagaStep.COMPENSATED
    assert saved_order.status is OrderStatus.FAILED
    assert len(saved_order.lines) == 2  # Order остаётся в истории со строками

    cart = await cart_repo.get_for_user(USER_ID)
    assert cart is not None
    assert {(line.product_id, line.quantity) for line in cart.lines} == {
        (line.product_id, line.quantity) for line in order.lines
    }
    assert all(line.unavailable_reason == "PAYMENT_DECLINED" for line in cart.lines)
    assert all(line.locked_by_order_id is None for line in cart.lines)


async def test_timeout_reason_is_carried_to_the_cart() -> None:
    order = _order_compensating(AuthorizationOutcome.TIMED_OUT)
    cart_repo = FakeCartRepository()
    handler = _handler(FakeOrderRepository([order]), cart_repo)

    await handler.execute(_manual(order.id))

    cart = await cart_repo.get_for_user(USER_ID)
    assert cart is not None
    assert {line.unavailable_reason for line in cart.lines} == {"PAYMENT_TIMED_OUT"}


async def test_lines_merge_into_an_existing_cart() -> None:
    order = _order_compensating(AuthorizationOutcome.DECLINED)
    cart = Cart.create(CartId.new_id(), user_id=USER_ID)
    cart.add_line(
        line_id=uuid.uuid4(),
        product_id=order.lines[0].product_id,
        quantity=4,
        now=datetime.now(UTC),
    )
    cart_repo = FakeCartRepository([cart])
    handler = _handler(FakeOrderRepository([order]), cart_repo)

    await handler.execute(_manual(order.id))

    quantities = {line.product_id: line.quantity for line in cart.lines}
    assert quantities[order.lines[0].product_id] == 4 + order.lines[0].quantity
    assert quantities[order.lines[1].product_id] == order.lines[1].quantity


async def test_repeated_release_does_not_double_quantities() -> None:
    order = _order_compensating(AuthorizationOutcome.DECLINED)
    order_repo = FakeOrderRepository([order])
    cart_repo = FakeCartRepository()
    handler = _handler(order_repo, cart_repo)
    await handler.execute(_manual(order.id))

    await handler.execute(_manual(order.id))

    assert len(order_repo.save_calls) == 1
    assert len(cart_repo.save_calls) == 1
    cart = await cart_repo.get_for_user(USER_ID)
    assert cart is not None
    assert {line.quantity for line in cart.lines} == {2, 1}


async def test_release_outside_compensating_changes_nothing() -> None:
    order = _order_awaiting_authorization()
    order_repo = FakeOrderRepository([order])
    cart_repo = FakeCartRepository()
    handler = _handler(order_repo, cart_repo)

    await handler.execute(_manual(order.id))

    assert order_repo.save_calls == []
    assert cart_repo.save_calls == []
    assert order.saga_step is OrderSagaStep.AWAITING_AUTHORIZATION
    assert await cart_repo.get_for_user(USER_ID) is None


# --- issue #377: истечение резерва -----------------------------------------


def _order_awaiting_allocation(authorization_id: uuid.UUID) -> Order:
    order = _order_awaiting_authorization()
    order.apply_authorization_result(
        outcome=AuthorizationOutcome.AUTHORIZED, authorization_id=authorization_id
    )
    return order


async def test_expiry_awaiting_authorization_expires_and_returns_lines() -> None:
    order = _order_awaiting_authorization()
    order_repo = FakeOrderRepository([order])
    cart_repo = FakeCartRepository()
    outbox = FakeSagaCommandOutboxRepository()
    handler = _handler(order_repo, cart_repo, outbox)

    await handler.execute(_expired(order.id))

    saved = await order_repo.get_by_id(order.id)
    assert saved is not None
    assert saved.status is OrderStatus.EXPIRED
    assert saved.failure_reason == "RESERVATION_EXPIRED"
    assert saved.saga_step is OrderSagaStep.COMPENSATED
    assert outbox.void_intents == []
    assert outbox.release_intents == []
    cart = await cart_repo.get_for_user(USER_ID)
    assert cart is not None
    assert {(line.product_id, line.quantity) for line in cart.lines} == {
        (line.product_id, line.quantity) for line in order.lines
    }
    assert {line.unavailable_reason for line in cart.lines} == {"RESERVATION_EXPIRED"}


async def test_expiry_awaiting_allocation_voids_the_stored_authorization() -> None:
    authorization_id = uuid.uuid4()
    order = _order_awaiting_allocation(authorization_id)
    order_repo = FakeOrderRepository([order])
    cart_repo = FakeCartRepository()
    outbox = FakeSagaCommandOutboxRepository()
    handler = _handler(order_repo, cart_repo, outbox)

    await handler.execute(_expired(order.id))

    assert order.status is OrderStatus.EXPIRED
    assert order.saga_step is OrderSagaStep.COMPENSATED
    assert outbox.void_intents == [
        VoidIntent(order_id=order.id, authorization_id=authorization_id)
    ]
    assert outbox.release_intents == []
    cart = await cart_repo.get_for_user(USER_ID)
    assert cart is not None
    assert len(cart.lines) == len(order.lines)


async def test_expiry_awaiting_reservation_keeps_the_step_and_the_cart() -> None:
    line = OrderLine(
        id=uuid.uuid4(), product_id=uuid.uuid4(), quantity=1, unit_price_kopecks=100
    )
    order = Order.create(uuid.uuid4(), user_id=USER_ID, lines=[line])
    order_repo = FakeOrderRepository([order])
    cart_repo = FakeCartRepository()
    outbox = FakeSagaCommandOutboxRepository()
    handler = _handler(order_repo, cart_repo, outbox)

    await handler.execute(_expired(order.id))

    assert order_repo.save_calls == [order]
    assert order.status is OrderStatus.EXPIRED
    assert order.saga_step is OrderSagaStep.AWAITING_RESERVATION
    assert outbox.void_intents == []
    assert cart_repo.save_calls == []


async def test_repeated_expiry_returns_lines_and_voids_once() -> None:
    order = _order_awaiting_allocation(uuid.uuid4())
    order_repo = FakeOrderRepository([order])
    cart_repo = FakeCartRepository()
    outbox = FakeSagaCommandOutboxRepository()
    handler = _handler(order_repo, cart_repo, outbox)
    await handler.execute(_expired(order.id))

    await handler.execute(_expired(order.id))

    assert len(order_repo.save_calls) == 1
    assert len(cart_repo.save_calls) == 1
    assert len(outbox.void_intents) == 1
    cart = await cart_repo.get_for_user(USER_ID)
    assert cart is not None
    assert {line.quantity for line in cart.lines} == {2, 1}  # не удвоено


async def test_expiry_while_compensating_a_cancel_completes_it() -> None:
    order = _order_awaiting_authorization()
    order.cancel()
    order_repo = FakeOrderRepository([order])
    cart_repo = FakeCartRepository()
    outbox = FakeSagaCommandOutboxRepository()
    handler = _handler(order_repo, cart_repo, outbox)

    await handler.execute(_expired(order.id))

    assert order.status is OrderStatus.CANCELLED
    assert order.failure_reason == "CANCELLED_BY_CUSTOMER"
    assert order.saga_step is OrderSagaStep.COMPENSATED
    assert outbox.void_intents == []
    cart = await cart_repo.get_for_user(USER_ID)
    assert cart is not None
    assert {line.unavailable_reason for line in cart.lines} == {"CANCELLED_BY_CUSTOMER"}


async def test_expiry_after_capture_was_requested_changes_nothing() -> None:
    order = _order_awaiting_allocation(uuid.uuid4())
    order.apply_allocation_result()
    order_repo = FakeOrderRepository([order])
    cart_repo = FakeCartRepository()
    outbox = FakeSagaCommandOutboxRepository()
    handler = _handler(order_repo, cart_repo, outbox)

    await handler.execute(_expired(order.id))

    assert order.status is OrderStatus.PENDING
    assert order.saga_step is OrderSagaStep.AWAITING_CAPTURE
    assert order_repo.save_calls == []
    assert cart_repo.save_calls == []
    assert outbox.void_intents == []


async def test_expiry_after_a_terminal_result_changes_nothing() -> None:
    order = _order_compensating(AuthorizationOutcome.DECLINED)
    order.complete_compensation()
    order_repo = FakeOrderRepository([order])
    cart_repo = FakeCartRepository()
    outbox = FakeSagaCommandOutboxRepository()
    handler = _handler(order_repo, cart_repo, outbox)

    await handler.execute(_expired(order.id))

    assert order.status is OrderStatus.FAILED
    assert order.failure_reason == "PAYMENT_DECLINED"
    assert order_repo.save_calls == []
    assert cart_repo.save_calls == []
