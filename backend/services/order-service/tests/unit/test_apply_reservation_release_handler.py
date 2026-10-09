"""ApplyReservationReleaseCommandHandler (issue #375, D6/AC3) — фейковые
repo: `inventory.released.v1` в `COMPENSATING` завершает компенсацию и
возвращает строки Order в Cart с причиной результата; Order остаётся
`FAILED` в истории; повтор и release в другом шаге — no-op."""

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


def _order_compensating(outcome: AuthorizationOutcome) -> Order:
    order = _order_awaiting_authorization()
    order.apply_authorization_result(outcome=outcome, authorization_id=uuid.uuid4())
    return order


async def test_unknown_order_is_a_no_op() -> None:
    order_repo = FakeOrderRepository()
    cart_repo = FakeCartRepository()
    handler = ApplyReservationReleaseCommandHandler(order_repo, cart_repo)

    await handler.execute(ApplyReservationReleaseCommand(order_id=uuid.uuid4()))

    assert order_repo.save_calls == []
    assert cart_repo.save_calls == []


async def test_release_in_compensating_returns_lines_to_cart_with_reason() -> None:
    order = _order_compensating(AuthorizationOutcome.DECLINED)
    order_repo = FakeOrderRepository([order])
    cart_repo = FakeCartRepository()
    handler = ApplyReservationReleaseCommandHandler(order_repo, cart_repo)

    await handler.execute(ApplyReservationReleaseCommand(order_id=order.id))

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
    handler = ApplyReservationReleaseCommandHandler(
        FakeOrderRepository([order]), cart_repo
    )

    await handler.execute(ApplyReservationReleaseCommand(order_id=order.id))

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
    handler = ApplyReservationReleaseCommandHandler(
        FakeOrderRepository([order]), cart_repo
    )

    await handler.execute(ApplyReservationReleaseCommand(order_id=order.id))

    quantities = {line.product_id: line.quantity for line in cart.lines}
    assert quantities[order.lines[0].product_id] == 4 + order.lines[0].quantity
    assert quantities[order.lines[1].product_id] == order.lines[1].quantity


async def test_repeated_release_does_not_double_quantities() -> None:
    order = _order_compensating(AuthorizationOutcome.DECLINED)
    order_repo = FakeOrderRepository([order])
    cart_repo = FakeCartRepository()
    handler = ApplyReservationReleaseCommandHandler(order_repo, cart_repo)
    await handler.execute(ApplyReservationReleaseCommand(order_id=order.id))

    await handler.execute(ApplyReservationReleaseCommand(order_id=order.id))

    assert len(order_repo.save_calls) == 1
    assert len(cart_repo.save_calls) == 1
    cart = await cart_repo.get_for_user(USER_ID)
    assert cart is not None
    assert {line.quantity for line in cart.lines} == {2, 1}


async def test_release_outside_compensating_changes_nothing() -> None:
    order = _order_awaiting_authorization()
    order_repo = FakeOrderRepository([order])
    cart_repo = FakeCartRepository()
    handler = ApplyReservationReleaseCommandHandler(order_repo, cart_repo)

    await handler.execute(ApplyReservationReleaseCommand(order_id=order.id))

    assert order_repo.save_calls == []
    assert cart_repo.save_calls == []
    assert order.saga_step is OrderSagaStep.AWAITING_AUTHORIZATION
    assert await cart_repo.get_for_user(USER_ID) is None
