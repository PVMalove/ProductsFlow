"""ApplyReservationResultCommandHandler (issue #372, D7, Seams for TDD #7) —
фейковый repo: partial/zero/full confirmed дают правильные переходы
Order+Cart; повторная доставка того же order_id-факта — no-op (не удваивает
удаление строк из Cart)."""

import uuid
from datetime import UTC, datetime

from application.commands.apply_reservation_result import (
    ApplyReservationResultCommand,
    ApplyReservationResultCommandHandler,
)
from domain.entities.cart import Cart
from domain.entities.order import Order, OrderLine, OrderSagaStep, OrderStatus
from domain.value_objects.cart_id import CartId
from tests.unit.fake_cart_repository import FakeCartRepository
from tests.unit.fake_order_repository import FakeOrderRepository

USER_ID = uuid.uuid4()


def _locked_cart_and_order(
    product_ids: list[uuid.UUID],
) -> tuple[Cart, Order, uuid.UUID]:
    cart = Cart.create(CartId.new_id(), user_id=USER_ID)
    for product_id in product_ids:
        cart.add_line(
            line_id=uuid.uuid4(),
            product_id=product_id,
            quantity=1,
            now=datetime.now(UTC),
        )
    order = Order.create(
        uuid.uuid4(),
        user_id=USER_ID,
        lines=[
            OrderLine(
                id=uuid.uuid4(), product_id=pid, quantity=1, unit_price_kopecks=100
            )
            for pid in product_ids
        ],
    )
    cart.lock_for_checkout(order_id=order.id)
    return cart, order, order.id


async def test_unknown_order_is_a_no_op() -> None:
    order_repo = FakeOrderRepository()
    cart_repo = FakeCartRepository()
    handler = ApplyReservationResultCommandHandler(order_repo, cart_repo)

    await handler.execute(
        ApplyReservationResultCommand(
            order_id=uuid.uuid4(), confirmed_product_ids=frozenset()
        )
    )

    assert order_repo.save_calls == []
    assert cart_repo.save_calls == []


async def test_zero_confirmed_marks_order_failed_and_unlocks_cart_untouched() -> None:
    product_id = uuid.uuid4()
    cart, order, order_id = _locked_cart_and_order([product_id])
    order_repo = FakeOrderRepository([order])
    cart_repo = FakeCartRepository([cart])
    handler = ApplyReservationResultCommandHandler(order_repo, cart_repo)

    await handler.execute(
        ApplyReservationResultCommand(
            order_id=order_id, confirmed_product_ids=frozenset()
        )
    )

    saved_order = await order_repo.get_by_id(order_id)
    assert saved_order is not None
    assert saved_order.status is OrderStatus.FAILED
    assert saved_order.failure_reason == "NO_ITEMS_AVAILABLE"
    assert len(saved_order.lines) == 1  # история сохранена, не тронута

    saved_cart = await cart_repo.get_for_user(USER_ID)
    assert saved_cart is not None
    assert len(saved_cart.lines) == 1  # ни одна строка не удалена
    assert saved_cart.lines[0].locked_by_order_id is None
    assert saved_cart.lines[0].unavailable_reason is None


async def test_partial_confirmed_trims_order_and_splits_cart() -> None:
    confirmed_id = uuid.uuid4()
    unavailable_id = uuid.uuid4()
    cart, order, order_id = _locked_cart_and_order([confirmed_id, unavailable_id])
    order_repo = FakeOrderRepository([order])
    cart_repo = FakeCartRepository([cart])
    handler = ApplyReservationResultCommandHandler(order_repo, cart_repo)

    await handler.execute(
        ApplyReservationResultCommand(
            order_id=order_id, confirmed_product_ids=frozenset({confirmed_id})
        )
    )

    saved_order = await order_repo.get_by_id(order_id)
    assert saved_order is not None
    assert saved_order.saga_step is OrderSagaStep.RESERVATION_CONFIRMED
    assert [line.product_id for line in saved_order.lines] == [confirmed_id]

    saved_cart = await cart_repo.get_for_user(USER_ID)
    assert saved_cart is not None
    assert len(saved_cart.lines) == 1
    assert saved_cart.lines[0].product_id == unavailable_id
    assert saved_cart.lines[0].locked_by_order_id is None
    assert saved_cart.lines[0].unavailable_reason == "insufficient_stock"


async def test_redelivery_of_the_same_fact_is_a_no_op() -> None:
    confirmed_id = uuid.uuid4()
    unavailable_id = uuid.uuid4()
    cart, order, order_id = _locked_cart_and_order([confirmed_id, unavailable_id])
    order_repo = FakeOrderRepository([order])
    cart_repo = FakeCartRepository([cart])
    handler = ApplyReservationResultCommandHandler(order_repo, cart_repo)
    command = ApplyReservationResultCommand(
        order_id=order_id, confirmed_product_ids=frozenset({confirmed_id})
    )
    await handler.execute(command)
    cart_saves_after_first = len(cart_repo.save_calls)

    # Redelivery с ДРУГИМ содержимым факта (было бы неправильно применить
    # его повторно) — saga_step guard в Order делает execute no-op.
    await handler.execute(
        ApplyReservationResultCommand(
            order_id=order_id, confirmed_product_ids=frozenset()
        )
    )

    assert len(cart_repo.save_calls) == cart_saves_after_first
    saved_order = await order_repo.get_by_id(order_id)
    assert saved_order is not None
    assert saved_order.saga_step is OrderSagaStep.RESERVATION_CONFIRMED
    assert [line.product_id for line in saved_order.lines] == [confirmed_id]
