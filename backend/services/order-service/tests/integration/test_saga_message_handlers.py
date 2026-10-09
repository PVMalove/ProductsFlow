"""Postgres-интеграция пути сообщений Saga (issue #375, AC1-AC4):
`handle_reservation_result`/`handle_authorization_result` прогоняются с
заглушкой `AbstractIncomingMessage` поверх настоящей БД — резерв ->
авторизация -> компенсация, повторная доставка и inbox-ключ по producer'у.
RabbitMQ не участвует: адаптеры получают сообщение напрямую."""

import json
import uuid
from dataclasses import dataclass
from datetime import UTC, datetime
from typing import cast

import pytest
from aio_pika.abc import AbstractIncomingMessage
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from api.workers.commands.authorization_result_handler import (
    handle_authorization_result,
)
from api.workers.commands.reservation_result_handler import (
    handle_reservation_result,
)
from domain.entities.order import Order, OrderLine, OrderSagaStep, OrderStatus
from infrastructure.db.cart_repository import CartRepository
from infrastructure.db.entity_configurations.models import (
    OrderLineModel,
    ReservationOutboxModel,
)
from infrastructure.db.order_repository import OrderRepository

pytestmark = pytest.mark.asyncio(loop_scope="session")

PAYMENT_METHOD_TOKEN = "success"


@dataclass
class _StubMessage:
    """Только поля, которые читают адаптеры order-worker'а."""

    type: str
    message_id: str
    body: bytes
    routing_key: str | None = None


def _message(
    event_type: str, message_id: int, payload: object
) -> AbstractIncomingMessage:
    return cast(
        "AbstractIncomingMessage",
        _StubMessage(
            type=event_type,
            message_id=str(message_id),
            body=json.dumps(payload).encode(),
        ),
    )


@dataclass(frozen=True)
class _Checkout:
    order_id: uuid.UUID
    user_id: uuid.UUID
    confirmed: OrderLine
    unavailable: OrderLine


async def _checked_out_order(
    session_factory: async_sessionmaker[AsyncSession],
) -> _Checkout:
    """Состояние сразу после checkout: Order с двумя строками (разные цены)
    и Cart, чьи строки заблокированы этим Order."""
    user_id = uuid.uuid4()
    confirmed = OrderLine(
        id=uuid.uuid4(), product_id=uuid.uuid4(), quantity=2, unit_price_kopecks=1_500
    )
    unavailable = OrderLine(
        id=uuid.uuid4(), product_id=uuid.uuid4(), quantity=1, unit_price_kopecks=9_900
    )
    order = Order.create(uuid.uuid4(), user_id=user_id, lines=[confirmed, unavailable])
    async with session_factory() as session:
        async with session.begin():
            await OrderRepository(session).save(order)
            cart_repo = CartRepository(session)
            cart = await cart_repo.get_or_create_for_user(user_id)
            for line in (confirmed, unavailable):
                cart.add_line(
                    line_id=uuid.uuid4(),
                    product_id=line.product_id,
                    quantity=line.quantity,
                    now=datetime.now(UTC),
                )
            cart.lock_for_checkout(order_id=order.id)
            await cart_repo.save(cart)
    return _Checkout(
        order_id=order.id, user_id=user_id, confirmed=confirmed, unavailable=unavailable
    )


async def _deliver_reserved(
    session_factory: async_sessionmaker[AsyncSession],
    checkout: _Checkout,
    *,
    message_id: int,
) -> None:
    await handle_reservation_result(
        _message(
            "inventory.reserved.v1",
            message_id,
            {
                "order_id": str(checkout.order_id),
                "expires_at": "2026-01-01T00:00:00+00:00",
                "confirmed_lines": [
                    {
                        "product_id": str(checkout.confirmed.product_id),
                        "quantity": checkout.confirmed.quantity,
                    }
                ],
                "unavailable_lines": [
                    {
                        "product_id": str(checkout.unavailable.product_id),
                        "requested_quantity": checkout.unavailable.quantity,
                    }
                ],
            },
        ),
        session_factory,
        payment_method_token=PAYMENT_METHOD_TOKEN,
    )


async def _deliver_authorization(
    session_factory: async_sessionmaker[AsyncSession],
    order_id: uuid.UUID,
    event_type: str,
    *,
    message_id: int,
    authorization_id: uuid.UUID | None = None,
) -> None:
    await handle_authorization_result(
        _message(
            event_type,
            message_id,
            {
                "authorization_id": str(authorization_id or uuid.uuid4()),
                "correlation_id": str(order_id),
                "causation_id": str(uuid.uuid4()),
            },
        ),
        session_factory,
    )


async def _deliver_released(
    session_factory: async_sessionmaker[AsyncSession],
    order_id: uuid.UUID,
    *,
    message_id: int,
) -> None:
    await handle_reservation_result(
        _message(
            "inventory.released.v1",
            message_id,
            {"order_id": str(order_id), "reason": "manual", "released_lines": []},
        ),
        session_factory,
        payment_method_token=PAYMENT_METHOD_TOKEN,
    )


async def _outbox_rows(
    session_factory: async_sessionmaker[AsyncSession], order_id: uuid.UUID
) -> list[ReservationOutboxModel]:
    async with session_factory() as session:
        return list(
            (
                await session.scalars(
                    select(ReservationOutboxModel).where(
                        ReservationOutboxModel.order_id == order_id
                    )
                )
            ).all()
        )


async def _load_order(
    session_factory: async_sessionmaker[AsyncSession], order_id: uuid.UUID
) -> Order:
    async with session_factory() as session:
        order = await OrderRepository(session).get_by_id(order_id)
    assert order is not None
    return order


async def test_partial_reservation_authorizes_only_the_confirmed_amount(
    saga_session_factory: async_sessionmaker[AsyncSession],
) -> None:
    checkout = await _checked_out_order(saga_session_factory)

    await _deliver_reserved(saga_session_factory, checkout, message_id=1)

    rows = await _outbox_rows(saga_session_factory, checkout.order_id)
    assert [row.command_type for row in rows] == ["payment.authorize.v1"]
    # 2 * 1500 за подтверждённую строку — не итог Cart 2 * 1500 + 9900.
    assert rows[0].payload == {
        "amount": 2 * 1_500,
        "payment_method_token": PAYMENT_METHOD_TOKEN,
    }
    order = await _load_order(saga_session_factory, checkout.order_id)
    assert order.saga_step is OrderSagaStep.AWAITING_AUTHORIZATION


async def test_authorized_result_moves_to_allocation_without_new_commands(
    saga_session_factory: async_sessionmaker[AsyncSession],
) -> None:
    checkout = await _checked_out_order(saga_session_factory)
    await _deliver_reserved(saga_session_factory, checkout, message_id=1)
    authorization_id = uuid.uuid4()

    await _deliver_authorization(
        saga_session_factory,
        checkout.order_id,
        "payment.authorized.v1",
        message_id=1,
        authorization_id=authorization_id,
    )

    order = await _load_order(saga_session_factory, checkout.order_id)
    assert order.status is OrderStatus.PENDING
    assert order.saga_step is OrderSagaStep.AWAITING_ALLOCATION
    assert order.payment_authorization_id == authorization_id
    rows = await _outbox_rows(saga_session_factory, checkout.order_id)
    assert [row.command_type for row in rows] == ["payment.authorize.v1"]


@pytest.mark.parametrize(
    ("event_type", "failure_reason"),
    [
        ("payment.authorization_declined.v1", "PAYMENT_DECLINED"),
        ("payment.authorization_timed_out.v1", "PAYMENT_TIMED_OUT"),
    ],
)
async def test_decline_or_timeout_compensates_and_returns_lines_to_cart(
    saga_session_factory: async_sessionmaker[AsyncSession],
    event_type: str,
    failure_reason: str,
) -> None:
    checkout = await _checked_out_order(saga_session_factory)
    await _deliver_reserved(saga_session_factory, checkout, message_id=1)

    await _deliver_authorization(
        saga_session_factory, checkout.order_id, event_type, message_id=2
    )

    order = await _load_order(saga_session_factory, checkout.order_id)
    assert order.status is OrderStatus.FAILED
    assert order.failure_reason == failure_reason
    assert order.saga_step is OrderSagaStep.COMPENSATING
    release_rows = [
        row
        for row in await _outbox_rows(saga_session_factory, checkout.order_id)
        if row.command_type == "inventory.release.v1"
    ]
    assert [row.payload for row in release_rows] == [
        {"order_id": str(checkout.order_id)}
    ]

    await _deliver_released(saga_session_factory, checkout.order_id, message_id=2)

    order = await _load_order(saga_session_factory, checkout.order_id)
    assert order.status is OrderStatus.FAILED
    assert order.saga_step is OrderSagaStep.COMPENSATED
    async with saga_session_factory() as session:
        order_line_ids = set(
            (
                await session.scalars(
                    select(OrderLineModel.id).where(
                        OrderLineModel.order_id == checkout.order_id
                    )
                )
            ).all()
        )
        cart = await CartRepository(session).get_for_user(checkout.user_id)
    assert order_line_ids == {checkout.confirmed.id}  # Order остаётся в истории
    assert cart is not None
    lines = {line.product_id: line for line in cart.lines}
    returned = lines[checkout.confirmed.product_id]
    assert returned.quantity == checkout.confirmed.quantity
    assert returned.unavailable_reason == failure_reason
    assert returned.locked_by_order_id is None
    # Строка, не подтверждённая резервом, осталась с причиной #372.
    assert lines[checkout.unavailable.product_id].unavailable_reason == (
        "insufficient_stock"
    )


async def test_redelivery_with_the_same_message_id_is_skipped(
    saga_session_factory: async_sessionmaker[AsyncSession],
) -> None:
    checkout = await _checked_out_order(saga_session_factory)
    await _deliver_reserved(saga_session_factory, checkout, message_id=10)
    await _deliver_reserved(saga_session_factory, checkout, message_id=10)
    await _deliver_authorization(
        saga_session_factory,
        checkout.order_id,
        "payment.authorization_declined.v1",
        message_id=20,
    )
    await _deliver_authorization(
        saga_session_factory,
        checkout.order_id,
        "payment.authorization_declined.v1",
        message_id=20,
    )

    rows = await _outbox_rows(saga_session_factory, checkout.order_id)
    assert sorted(row.command_type for row in rows) == [
        "inventory.release.v1",
        "payment.authorize.v1",
    ]


async def test_repeated_results_with_other_message_ids_are_no_ops(
    saga_session_factory: async_sessionmaker[AsyncSession],
) -> None:
    checkout = await _checked_out_order(saga_session_factory)
    await _deliver_reserved(saga_session_factory, checkout, message_id=1)
    await _deliver_reserved(saga_session_factory, checkout, message_id=2)
    await _deliver_authorization(
        saga_session_factory,
        checkout.order_id,
        "payment.authorization_timed_out.v1",
        message_id=1,
    )
    await _deliver_authorization(
        saga_session_factory,
        checkout.order_id,
        "payment.authorization_declined.v1",
        message_id=2,
    )
    await _deliver_released(saga_session_factory, checkout.order_id, message_id=3)
    await _deliver_released(saga_session_factory, checkout.order_id, message_id=4)

    rows = await _outbox_rows(saga_session_factory, checkout.order_id)
    assert sorted(row.command_type for row in rows) == [
        "inventory.release.v1",
        "payment.authorize.v1",
    ]
    order = await _load_order(saga_session_factory, checkout.order_id)
    assert order.failure_reason == "PAYMENT_TIMED_OUT"
    async with saga_session_factory() as session:
        cart = await CartRepository(session).get_for_user(checkout.user_id)
    assert cart is not None
    returned = next(
        line for line in cart.lines if line.product_id == checkout.confirmed.product_id
    )
    assert returned.quantity == checkout.confirmed.quantity  # не удвоено


async def test_inventory_and_payment_events_with_the_same_message_id_both_apply(
    saga_session_factory: async_sessionmaker[AsyncSession],
) -> None:
    checkout = await _checked_out_order(saga_session_factory)

    await _deliver_reserved(saga_session_factory, checkout, message_id=7)
    await _deliver_authorization(
        saga_session_factory,
        checkout.order_id,
        "payment.authorization_declined.v1",
        message_id=7,
    )

    order = await _load_order(saga_session_factory, checkout.order_id)
    assert order.saga_step is OrderSagaStep.COMPENSATING
    assert order.failure_reason == "PAYMENT_DECLINED"
