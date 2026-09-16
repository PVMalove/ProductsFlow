"""CheckoutCommandHandler (issue #372, D5, Seams for TDD #6) — фейковый
UoW+repo+CatalogClient, без БД/AMQP: оркестрация целиком — CATALOG_UNAVAILABLE
блокирует checkout ничего не сохраняя, идемпотентный replay не повторяет
quote, конфликт fingerprint даёт 409-эквивалент, happy path создаёт Order,
блокирует Cart и ставит reservation_outbox intent до commit."""

import uuid
from datetime import UTC, datetime

import pytest
from kernel_platform.security import Actor, ActorRole

from application.commands.checkout import CheckoutCommand, CheckoutCommandHandler
from application.errors import CatalogUnavailableError
from domain.entities.cart import Cart
from domain.entities.idempotency_key import IdempotencyKeyRecord
from domain.entities.order import Order, OrderLine
from domain.value_objects.cart_id import CartId
from tests.unit.fake_cart_repository import FakeCartRepository
from tests.unit.fake_catalog_client import FakeCatalogClient
from tests.unit.fake_checkout_unit_of_work import FakeCheckoutUnitOfWork
from tests.unit.fake_idempotency_key_repository import FakeIdempotencyKeyRepository
from tests.unit.fake_order_repository import FakeOrderRepository
from tests.unit.fake_reservation_outbox_repository import (
    FakeReservationOutboxRepository,
)

ACTOR = Actor(id=uuid.uuid4(), role=ActorRole.USER)


def _cart_with_one_line(product_id: uuid.UUID | None = None) -> Cart:
    cart = Cart.create(CartId.new_id(), user_id=ACTOR.id)
    cart.add_line(
        line_id=uuid.uuid4(),
        product_id=product_id or uuid.uuid4(),
        quantity=2,
        now=datetime.now(UTC),
    )
    return cart


def _handler(
    *,
    cart: Cart | None = None,
    catalog: FakeCatalogClient | None = None,
) -> tuple[CheckoutCommandHandler, FakeCheckoutUnitOfWork]:
    cart_repo = FakeCartRepository([cart] if cart is not None else [])
    order_repo = FakeOrderRepository()
    idempotency_repo = FakeIdempotencyKeyRepository()
    outbox_repo = FakeReservationOutboxRepository()
    uow = FakeCheckoutUnitOfWork(
        carts=cart_repo,
        orders=order_repo,
        idempotency_keys=idempotency_repo,
        reservation_outbox=outbox_repo,
    )
    handler = CheckoutCommandHandler(uow, catalog or FakeCatalogClient())
    return handler, uow


async def test_empty_cart_fails_without_calling_catalog() -> None:
    catalog = FakeCatalogClient()
    handler, uow = _handler(cart=None, catalog=catalog)

    result = await handler.execute(
        CheckoutCommand(actor=ACTOR, idempotency_key="key-1", bearer_token="t")
    )

    assert result.is_err
    assert result.error.code == "empty_cart"
    assert catalog.calls == []
    assert uow.committed is False


async def test_catalog_unavailable_raises_without_persisting_anything() -> None:
    cart = _cart_with_one_line()
    catalog = FakeCatalogClient(unavailable_product_ids={cart.lines[0].product_id})
    handler, uow = _handler(cart=cart, catalog=catalog)

    with pytest.raises(CatalogUnavailableError):
        await handler.execute(
            CheckoutCommand(actor=ACTOR, idempotency_key="key-1", bearer_token="t")
        )

    assert uow.committed is False
    assert uow.orders.save_calls == []
    assert uow.idempotency_keys.save_calls == []
    assert uow.reservation_outbox.enqueue_calls == []
    # Cart не заблокирована — checkout не дошёл до selection freeze.
    assert cart.lines[0].locked_by_order_id is None


async def test_happy_path_creates_order_locks_cart_and_enqueues_reservation() -> None:
    cart = _cart_with_one_line()
    product_id = cart.lines[0].product_id
    catalog = FakeCatalogClient(prices_by_product_id={product_id: 4_500})
    handler, uow = _handler(cart=cart, catalog=catalog)

    result = await handler.execute(
        CheckoutCommand(actor=ACTOR, idempotency_key="key-1", bearer_token="t")
    )

    assert result.is_ok
    order_view = result.value
    assert len(order_view.lines) == 1
    assert order_view.lines[0].unit_price_kopecks == 4_500
    assert order_view.status == "pending"
    assert uow.committed is True
    assert len(uow.orders.save_calls) == 1
    assert len(uow.idempotency_keys.save_calls) == 1
    assert len(uow.reservation_outbox.enqueue_calls) == 1
    assert cart.lines[0].locked_by_order_id == order_view.id
    assert len(catalog.calls) == 1


async def test_identical_replay_returns_the_same_order_without_requoting() -> None:
    cart = _cart_with_one_line()
    product_id = cart.lines[0].product_id
    catalog = FakeCatalogClient(prices_by_product_id={product_id: 4_500})
    handler, uow = _handler(cart=cart, catalog=catalog)
    command = CheckoutCommand(actor=ACTOR, idempotency_key="key-1", bearer_token="t")

    first = await handler.execute(command)
    second = await handler.execute(command)

    assert first.is_ok
    assert second.is_ok
    assert second.value.id == first.value.id
    assert len(catalog.calls) == 1
    assert len(uow.orders.save_calls) == 1
    assert len(uow.reservation_outbox.enqueue_calls) == 1


async def test_same_key_different_cart_conflicts() -> None:
    cart = _cart_with_one_line()
    catalog = FakeCatalogClient()
    handler, uow = _handler(cart=cart, catalog=catalog)
    first_result = await handler.execute(
        CheckoutCommand(actor=ACTOR, idempotency_key="key-1", bearer_token="t")
    )
    assert first_result.is_ok

    # Корзина изменилась после первого checkout того же ключа (новая строка
    # добавлена напрямую в fake — тот же user, тот же Idempotency-Key).
    cart.add_line(
        line_id=uuid.uuid4(), product_id=uuid.uuid4(), quantity=1, now=datetime.now(UTC)
    )

    result = await handler.execute(
        CheckoutCommand(actor=ACTOR, idempotency_key="key-1", bearer_token="t")
    )

    assert result.is_err
    assert result.error.code == "idempotency_key_conflict"


async def test_different_key_is_independent_even_with_identical_cart() -> None:
    order_id = uuid.uuid4()
    product_id = uuid.uuid4()
    order = Order.create(
        order_id,
        user_id=ACTOR.id,
        lines=[
            OrderLine(
                id=uuid.uuid4(),
                product_id=product_id,
                quantity=1,
                unit_price_kopecks=1_000,
            )
        ],
    )
    cart = _cart_with_one_line(product_id)
    cart_repo = FakeCartRepository([cart])
    order_repo = FakeOrderRepository([order])
    idempotency_repo = FakeIdempotencyKeyRepository()
    await idempotency_repo.save(
        IdempotencyKeyRecord(
            user_id=ACTOR.id,
            key="key-1",
            request_fingerprint="stale-fingerprint-not-matching-current-cart",
            order_id=order_id,
            created_at=datetime.now(UTC),
        )
    )
    outbox_repo = FakeReservationOutboxRepository()
    uow = FakeCheckoutUnitOfWork(
        carts=cart_repo,
        orders=order_repo,
        idempotency_keys=idempotency_repo,
        reservation_outbox=outbox_repo,
    )
    handler = CheckoutCommandHandler(uow, FakeCatalogClient())

    result = await handler.execute(
        CheckoutCommand(actor=ACTOR, idempotency_key="key-2", bearer_token="t")
    )

    assert result.is_ok
    assert result.value.id != order_id
