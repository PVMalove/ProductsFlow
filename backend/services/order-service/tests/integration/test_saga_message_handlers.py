"""Postgres-интеграция пути сообщений Saga (issue #375, AC1-AC4; issue #376,
AC1-AC4; issue #377, AC1-AC4): `handle_inventory_event`/`handle_payment_event`
прогоняются с заглушкой `AbstractIncomingMessage` поверх настоящей БД —
резерв -> авторизация -> allocation -> capture либо компенсация, отмена
владельцем и истечение резерва, повторная доставка, результаты не в своём
шаге и inbox-ключ по producer'у. RabbitMQ не участвует: адаптеры получают
сообщение напрямую."""

import json
import uuid
from dataclasses import dataclass
from datetime import UTC, datetime
from typing import cast

import pytest
from aio_pika.abc import AbstractIncomingMessage
from kernel_domain.result import Result
from kernel_platform.outbox.models import OutboxMessage
from kernel_platform.security import Actor, ActorRole
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from api.workers.commands.inventory_event_handler import (
    handle_inventory_event,
)
from api.workers.commands.payment_event_handler import (
    handle_payment_event,
)
from application.commands.cancel_order import (
    CancelOrderCommand,
    CancelOrderCommandHandler,
)
from contracts.order import OrderView
from domain.entities.cart_line import CartLine
from domain.entities.order import Order, OrderLine, OrderSagaStep, OrderStatus
from infrastructure.db.cart_repository import CartRepository
from infrastructure.db.entity_configurations.models import (
    OrderLineModel,
    OrderSagaTransitionModel,
    ProcessedMessageModel,
    ReservationOutboxModel,
)
from infrastructure.db.order_repository import OrderRepository
from infrastructure.db.unit_of_work import SqlOrderServiceUnitOfWork

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
    await handle_inventory_event(
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
    await handle_payment_event(
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
    reason: str = "manual",
) -> None:
    await handle_inventory_event(
        _message(
            "inventory.released.v1",
            message_id,
            {"order_id": str(order_id), "reason": reason, "released_lines": []},
        ),
        session_factory,
        payment_method_token=PAYMENT_METHOD_TOKEN,
    )


async def _deliver_allocated(
    session_factory: async_sessionmaker[AsyncSession],
    checkout: _Checkout,
    *,
    message_id: int,
) -> None:
    await handle_inventory_event(
        _message(
            "inventory.allocated.v1",
            message_id,
            {
                "order_id": str(checkout.order_id),
                "allocated_lines": [
                    {
                        "product_id": str(checkout.confirmed.product_id),
                        "quantity": checkout.confirmed.quantity,
                    }
                ],
            },
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


async def test_authorized_result_moves_to_allocation_and_requests_allocation(
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
    assert sorted(row.command_type for row in rows) == [
        "inventory.allocate.v1",
        "payment.authorize.v1",
    ]
    allocate_rows = [row for row in rows if row.command_type == "inventory.allocate.v1"]
    assert [row.payload for row in allocate_rows] == [
        {"order_id": str(checkout.order_id)}
    ]


async def _authorized_order(
    session_factory: async_sessionmaker[AsyncSession],
    authorization_id: uuid.UUID,
) -> _Checkout:
    """Состояние `AWAITING_ALLOCATION`: резерв и авторизация применены."""
    checkout = await _checked_out_order(session_factory)
    await _deliver_reserved(session_factory, checkout, message_id=1)
    await _deliver_authorization(
        session_factory,
        checkout.order_id,
        "payment.authorized.v1",
        message_id=1,
        authorization_id=authorization_id,
    )
    return checkout


def _rows_of_type(
    rows: list[ReservationOutboxModel], command_type: str
) -> list[ReservationOutboxModel]:
    return [row for row in rows if row.command_type == command_type]


async def test_allocated_result_moves_to_capture_and_requests_capture(
    saga_session_factory: async_sessionmaker[AsyncSession],
) -> None:
    authorization_id = uuid.uuid4()
    checkout = await _authorized_order(saga_session_factory, authorization_id)

    await _deliver_allocated(saga_session_factory, checkout, message_id=2)

    order = await _load_order(saga_session_factory, checkout.order_id)
    assert order.status is OrderStatus.PENDING
    assert order.saga_step is OrderSagaStep.AWAITING_CAPTURE
    rows = await _outbox_rows(saga_session_factory, checkout.order_id)
    capture_rows = _rows_of_type(rows, "payment.capture.v1")
    assert [row.payload for row in capture_rows] == [
        {"authorization_id": str(authorization_id)}
    ]


async def test_allocated_result_before_authorization_changes_nothing(
    saga_session_factory: async_sessionmaker[AsyncSession],
) -> None:
    checkout = await _checked_out_order(saga_session_factory)
    await _deliver_reserved(saga_session_factory, checkout, message_id=1)

    await _deliver_allocated(saga_session_factory, checkout, message_id=2)

    order = await _load_order(saga_session_factory, checkout.order_id)
    assert order.status is OrderStatus.PENDING
    assert order.saga_step is OrderSagaStep.AWAITING_AUTHORIZATION
    rows = await _outbox_rows(saga_session_factory, checkout.order_id)
    assert [row.command_type for row in rows] == ["payment.authorize.v1"]


async def test_repeated_allocated_result_requests_one_capture(
    saga_session_factory: async_sessionmaker[AsyncSession],
) -> None:
    checkout = await _authorized_order(saga_session_factory, uuid.uuid4())
    await _deliver_allocated(saga_session_factory, checkout, message_id=2)
    journal_before = await _journal(saga_session_factory, checkout.order_id)

    # Та же доставка (тот же message_id) и тот же факт с другим message_id.
    await _deliver_allocated(saga_session_factory, checkout, message_id=2)
    await _deliver_allocated(saga_session_factory, checkout, message_id=3)

    rows = await _outbox_rows(saga_session_factory, checkout.order_id)
    assert len(_rows_of_type(rows, "payment.capture.v1")) == 1
    assert len(_rows_of_type(rows, "inventory.allocate.v1")) == 1
    assert await _journal(saga_session_factory, checkout.order_id) == journal_before
    assert await _event_outbox_rows(saga_session_factory, checkout.order_id) == []
    order = await _load_order(saga_session_factory, checkout.order_id)
    assert order.saga_step is OrderSagaStep.AWAITING_CAPTURE


async def test_declined_authorization_requests_no_allocation(
    saga_session_factory: async_sessionmaker[AsyncSession],
) -> None:
    checkout = await _checked_out_order(saga_session_factory)
    await _deliver_reserved(saga_session_factory, checkout, message_id=1)
    await _deliver_authorization(
        saga_session_factory,
        checkout.order_id,
        "payment.authorization_declined.v1",
        message_id=1,
    )

    await _deliver_allocated(saga_session_factory, checkout, message_id=2)

    rows = await _outbox_rows(saga_session_factory, checkout.order_id)
    assert _rows_of_type(rows, "inventory.allocate.v1") == []
    assert _rows_of_type(rows, "payment.capture.v1") == []
    order = await _load_order(saga_session_factory, checkout.order_id)
    assert order.saga_step is OrderSagaStep.COMPENSATING


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


async def _deliver_captured(
    session_factory: async_sessionmaker[AsyncSession],
    order_id: uuid.UUID,
    *,
    authorization_id: uuid.UUID,
    message_id: int,
    causation_id: uuid.UUID | None = None,
) -> None:
    await handle_payment_event(
        _message(
            "payment.captured.v1",
            message_id,
            {
                "authorization_id": str(authorization_id),
                "correlation_id": str(order_id),
                "causation_id": str(causation_id or uuid.uuid4()),
            },
        ),
        session_factory,
    )


async def _event_outbox_rows(
    session_factory: async_sessionmaker[AsyncSession], order_id: uuid.UUID
) -> list[OutboxMessage]:
    async with session_factory() as session:
        return list(
            (
                await session.scalars(
                    select(OutboxMessage).where(OutboxMessage.aggregate_id == order_id)
                )
            ).all()
        )


async def _journal(
    session_factory: async_sessionmaker[AsyncSession], order_id: uuid.UUID
) -> list[tuple[str, str]]:
    async with session_factory() as session:
        rows = (
            await session.scalars(
                select(OrderSagaTransitionModel)
                .where(OrderSagaTransitionModel.order_id == order_id)
                .order_by(OrderSagaTransitionModel.id)
            )
        ).all()
    return [(row.saga_step, row.status) for row in rows]


async def _allocated_order(
    session_factory: async_sessionmaker[AsyncSession],
    authorization_id: uuid.UUID,
) -> _Checkout:
    """Состояние `AWAITING_CAPTURE`: резерв, авторизация и allocation
    применены (inventory message_id 1-2, payment message_id 1)."""
    checkout = await _authorized_order(session_factory, authorization_id)
    await _deliver_allocated(session_factory, checkout, message_id=2)
    return checkout


async def test_captured_result_completes_order_with_history_and_order_completed(
    saga_session_factory: async_sessionmaker[AsyncSession],
) -> None:
    authorization_id = uuid.uuid4()
    checkout = await _allocated_order(saga_session_factory, authorization_id)
    capture_command_id = uuid.uuid4()

    await _deliver_captured(
        saga_session_factory,
        checkout.order_id,
        authorization_id=authorization_id,
        message_id=2,
        causation_id=capture_command_id,
    )

    order = await _load_order(saga_session_factory, checkout.order_id)
    assert order.status is OrderStatus.COMPLETED
    assert order.saga_step is OrderSagaStep.CAPTURED
    assert OrderView.from_domain(order).status == "completed"
    assert await _journal(saga_session_factory, checkout.order_id) == [
        ("awaiting_reservation", "pending"),
        ("awaiting_authorization", "pending"),
        ("awaiting_allocation", "pending"),
        ("awaiting_capture", "pending"),
        ("captured", "completed"),
    ]
    events = await _event_outbox_rows(saga_session_factory, checkout.order_id)
    assert len(events) == 1
    event = events[0]
    assert event.event_type == "order.completed.v1"
    assert event.aggregate_type == "Order"
    assert event.aggregate_id == checkout.order_id
    assert event.published_at is None
    assert set(event.payload) == {"order_id", "correlation_id", "causation_id"}
    assert event.payload["order_id"] == str(checkout.order_id)
    assert event.payload["correlation_id"] == str(checkout.order_id)
    assert event.payload["causation_id"] == str(capture_command_id)
    assert str(checkout.user_id) not in json.dumps(event.payload)


async def test_repeated_captured_result_adds_no_event_command_or_history(
    saga_session_factory: async_sessionmaker[AsyncSession],
) -> None:
    authorization_id = uuid.uuid4()
    checkout = await _allocated_order(saga_session_factory, authorization_id)
    await _deliver_captured(
        saga_session_factory,
        checkout.order_id,
        authorization_id=authorization_id,
        message_id=2,
    )
    commands_before = await _outbox_rows(saga_session_factory, checkout.order_id)
    journal_before = await _journal(saga_session_factory, checkout.order_id)

    # Та же доставка (тот же message_id) и тот же факт с другим message_id.
    for message_id in (2, 3):
        await _deliver_captured(
            saga_session_factory,
            checkout.order_id,
            authorization_id=authorization_id,
            message_id=message_id,
        )

    assert len(await _event_outbox_rows(saga_session_factory, checkout.order_id)) == 1
    commands_after = await _outbox_rows(saga_session_factory, checkout.order_id)
    assert len(commands_after) == len(commands_before)
    assert await _journal(saga_session_factory, checkout.order_id) == journal_before
    order = await _load_order(saga_session_factory, checkout.order_id)
    assert order.status is OrderStatus.COMPLETED


async def test_captured_result_for_another_authorization_does_not_complete_the_order(
    saga_session_factory: async_sessionmaker[AsyncSession],
) -> None:
    checkout = await _allocated_order(saga_session_factory, uuid.uuid4())
    journal_before = await _journal(saga_session_factory, checkout.order_id)

    await _deliver_captured(
        saga_session_factory,
        checkout.order_id,
        authorization_id=uuid.uuid4(),
        message_id=2,
    )

    order = await _load_order(saga_session_factory, checkout.order_id)
    assert order.status is OrderStatus.PENDING
    assert order.saga_step is OrderSagaStep.AWAITING_CAPTURE
    assert await _journal(saga_session_factory, checkout.order_id) == journal_before
    assert await _event_outbox_rows(saga_session_factory, checkout.order_id) == []


async def test_captured_result_before_allocation_does_not_advance_the_order(
    saga_session_factory: async_sessionmaker[AsyncSession],
) -> None:
    authorization_id = uuid.uuid4()
    checkout = await _authorized_order(saga_session_factory, authorization_id)

    await _deliver_captured(
        saga_session_factory,
        checkout.order_id,
        authorization_id=authorization_id,
        message_id=2,
    )

    order = await _load_order(saga_session_factory, checkout.order_id)
    assert order.status is OrderStatus.PENDING
    assert order.saga_step is OrderSagaStep.AWAITING_ALLOCATION
    assert await _event_outbox_rows(saga_session_factory, checkout.order_id) == []

    # Позднее allocation продолжает Saga обычным путём.
    await _deliver_allocated(saga_session_factory, checkout, message_id=2)

    order = await _load_order(saga_session_factory, checkout.order_id)
    assert order.saga_step is OrderSagaStep.AWAITING_CAPTURE
    rows = await _outbox_rows(saga_session_factory, checkout.order_id)
    assert len(_rows_of_type(rows, "payment.capture.v1")) == 1


async def test_allocated_result_after_capture_is_a_no_op(
    saga_session_factory: async_sessionmaker[AsyncSession],
) -> None:
    authorization_id = uuid.uuid4()
    checkout = await _allocated_order(saga_session_factory, authorization_id)
    await _deliver_captured(
        saga_session_factory,
        checkout.order_id,
        authorization_id=authorization_id,
        message_id=2,
    )
    journal_before = await _journal(saga_session_factory, checkout.order_id)

    await _deliver_allocated(saga_session_factory, checkout, message_id=3)

    order = await _load_order(saga_session_factory, checkout.order_id)
    assert order.status is OrderStatus.COMPLETED
    assert order.saga_step is OrderSagaStep.CAPTURED
    rows = await _outbox_rows(saga_session_factory, checkout.order_id)
    assert len(_rows_of_type(rows, "payment.capture.v1")) == 1
    assert await _journal(saga_session_factory, checkout.order_id) == journal_before
    assert len(await _event_outbox_rows(saga_session_factory, checkout.order_id)) == 1


# --- issue #377: отмена владельцем и истечение резерва ----------------------


async def _cancel(
    session_factory: async_sessionmaker[AsyncSession], checkout: _Checkout
) -> Result[OrderView]:
    async with session_factory() as session:
        return await CancelOrderCommandHandler(
            SqlOrderServiceUnitOfWork(session)
        ).execute(
            CancelOrderCommand(
                actor=Actor(id=checkout.user_id, role=ActorRole.USER),
                order_id=checkout.order_id,
            )
        )


async def _deliver_voided(
    session_factory: async_sessionmaker[AsyncSession],
    order_id: uuid.UUID,
    *,
    authorization_id: uuid.UUID,
    message_id: int,
) -> None:
    await handle_payment_event(
        _message(
            "payment.voided.v1",
            message_id,
            {
                "authorization_id": str(authorization_id),
                "correlation_id": str(order_id),
                "causation_id": str(uuid.uuid4()),
            },
        ),
        session_factory,
    )


async def _cart_lines(
    session_factory: async_sessionmaker[AsyncSession], user_id: uuid.UUID
) -> dict[uuid.UUID, CartLine]:
    async with session_factory() as session:
        cart = await CartRepository(session).get_for_user(user_id)
    assert cart is not None
    return {line.product_id: line for line in cart.lines}


def _payloads(
    rows: list[ReservationOutboxModel], command_type: str
) -> list[dict[str, object]]:
    return [row.payload for row in _rows_of_type(rows, command_type)]


async def test_cancel_awaiting_authorization_releases_then_returns_lines(
    saga_session_factory: async_sessionmaker[AsyncSession],
) -> None:
    checkout = await _checked_out_order(saga_session_factory)
    # Результат резерва ДО отмены: строка уже ушла из Cart в Order.
    await _deliver_reserved(saga_session_factory, checkout, message_id=1)

    result = await _cancel(saga_session_factory, checkout)

    assert result.is_ok
    assert result.value.status == "cancelled"
    order = await _load_order(saga_session_factory, checkout.order_id)
    assert order.status is OrderStatus.CANCELLED
    assert order.failure_reason == "CANCELLED_BY_CUSTOMER"
    assert order.saga_step is OrderSagaStep.COMPENSATING
    rows = await _outbox_rows(saga_session_factory, checkout.order_id)
    assert _payloads(rows, "inventory.release.v1") == [
        {"order_id": str(checkout.order_id)}
    ]
    assert _rows_of_type(rows, "payment.void.v1") == []
    # Строки возвращаются только по факту release.
    lines = await _cart_lines(saga_session_factory, checkout.user_id)
    assert checkout.confirmed.product_id not in lines

    await _deliver_released(saga_session_factory, checkout.order_id, message_id=2)

    order = await _load_order(saga_session_factory, checkout.order_id)
    assert order.status is OrderStatus.CANCELLED
    assert order.saga_step is OrderSagaStep.COMPENSATED
    lines = await _cart_lines(saga_session_factory, checkout.user_id)
    returned = lines[checkout.confirmed.product_id]
    assert returned.quantity == checkout.confirmed.quantity
    assert returned.unavailable_reason == "CANCELLED_BY_CUSTOMER"
    assert returned.locked_by_order_id is None
    assert lines[checkout.unavailable.product_id].unavailable_reason == (
        "insufficient_stock"
    )
    assert await _journal(saga_session_factory, checkout.order_id) == [
        ("awaiting_reservation", "pending"),
        ("awaiting_authorization", "pending"),
        ("compensating", "cancelled"),
        ("compensated", "cancelled"),
    ]


async def test_cancel_awaiting_allocation_voids_and_releases_then_returns_lines(
    saga_session_factory: async_sessionmaker[AsyncSession],
) -> None:
    authorization_id = uuid.uuid4()
    # Авторизация ДО отмены: Order хранит authorization_id.
    checkout = await _authorized_order(saga_session_factory, authorization_id)

    result = await _cancel(saga_session_factory, checkout)

    assert result.is_ok
    rows = await _outbox_rows(saga_session_factory, checkout.order_id)
    assert _payloads(rows, "payment.void.v1") == [
        {"authorization_id": str(authorization_id)}
    ]
    assert _payloads(rows, "inventory.release.v1") == [
        {"order_id": str(checkout.order_id)}
    ]

    # Позднее allocation не запрашивает capture.
    await _deliver_allocated(saga_session_factory, checkout, message_id=2)
    await _deliver_released(saga_session_factory, checkout.order_id, message_id=3)
    await _deliver_voided(
        saga_session_factory,
        checkout.order_id,
        authorization_id=authorization_id,
        message_id=2,
    )

    order = await _load_order(saga_session_factory, checkout.order_id)
    assert order.status is OrderStatus.CANCELLED
    assert order.saga_step is OrderSagaStep.COMPENSATED
    rows = await _outbox_rows(saga_session_factory, checkout.order_id)
    assert _rows_of_type(rows, "payment.capture.v1") == []
    assert len(_rows_of_type(rows, "payment.void.v1")) == 1
    lines = await _cart_lines(saga_session_factory, checkout.user_id)
    assert lines[checkout.confirmed.product_id].unavailable_reason == (
        "CANCELLED_BY_CUSTOMER"
    )


async def test_reservation_result_after_cancel_releases_without_authorization(
    saga_session_factory: async_sessionmaker[AsyncSession],
) -> None:
    checkout = await _checked_out_order(saga_session_factory)
    result = await _cancel(saga_session_factory, checkout)
    assert result.is_ok
    assert await _outbox_rows(saga_session_factory, checkout.order_id) == []
    order = await _load_order(saga_session_factory, checkout.order_id)
    assert order.saga_step is OrderSagaStep.AWAITING_RESERVATION

    # Результат резерва ПОСЛЕ отмены.
    await _deliver_reserved(saga_session_factory, checkout, message_id=1)

    order = await _load_order(saga_session_factory, checkout.order_id)
    assert order.status is OrderStatus.CANCELLED
    assert order.saga_step is OrderSagaStep.COMPENSATING
    assert [line.product_id for line in order.lines] == [checkout.confirmed.product_id]
    rows = await _outbox_rows(saga_session_factory, checkout.order_id)
    assert [row.command_type for row in rows] == ["inventory.release.v1"]

    await _deliver_released(saga_session_factory, checkout.order_id, message_id=2)

    order = await _load_order(saga_session_factory, checkout.order_id)
    assert order.saga_step is OrderSagaStep.COMPENSATED
    lines = await _cart_lines(saga_session_factory, checkout.user_id)
    assert lines[checkout.confirmed.product_id].unavailable_reason == (
        "CANCELLED_BY_CUSTOMER"
    )
    assert lines[checkout.confirmed.product_id].quantity == checkout.confirmed.quantity
    assert all(line.locked_by_order_id is None for line in lines.values())


async def test_empty_reservation_result_after_cancel_unlocks_the_cart(
    saga_session_factory: async_sessionmaker[AsyncSession],
) -> None:
    checkout = await _checked_out_order(saga_session_factory)
    await _cancel(saga_session_factory, checkout)

    await handle_inventory_event(
        _message(
            "inventory.reserved.v1",
            1,
            {
                "order_id": str(checkout.order_id),
                "confirmed_lines": [],
                "unavailable_lines": [],
            },
        ),
        saga_session_factory,
        payment_method_token=PAYMENT_METHOD_TOKEN,
    )

    order = await _load_order(saga_session_factory, checkout.order_id)
    assert order.status is OrderStatus.CANCELLED
    assert order.saga_step is OrderSagaStep.COMPENSATED
    assert await _outbox_rows(saga_session_factory, checkout.order_id) == []
    lines = await _cart_lines(saga_session_factory, checkout.user_id)
    assert set(lines) == {
        checkout.confirmed.product_id,
        checkout.unavailable.product_id,
    }
    assert all(line.locked_by_order_id is None for line in lines.values())
    assert all(line.unavailable_reason is None for line in lines.values())


async def test_expiry_before_a_late_reservation_result_completes_the_cancel(
    saga_session_factory: async_sessionmaker[AsyncSession],
) -> None:
    checkout = await _checked_out_order(saga_session_factory)
    await _cancel(saga_session_factory, checkout)

    # Истечение резерва обгоняет его результат (inventory.reserved.v1
    # задержан, например повтор из DLQ): inventory уже освободил резерв.
    await _deliver_released(
        saga_session_factory, checkout.order_id, message_id=2, reason="expired"
    )

    order = await _load_order(saga_session_factory, checkout.order_id)
    assert order.status is OrderStatus.CANCELLED
    assert order.failure_reason == "CANCELLED_BY_CUSTOMER"
    assert order.saga_step is OrderSagaStep.COMPENSATED
    lines = await _cart_lines(saga_session_factory, checkout.user_id)
    assert all(line.locked_by_order_id is None for line in lines.values())

    # Поздний результат резерва и повтор истечения с другим message_id.
    await _deliver_reserved(saga_session_factory, checkout, message_id=1)
    await _deliver_released(
        saga_session_factory, checkout.order_id, message_id=3, reason="expired"
    )

    order = await _load_order(saga_session_factory, checkout.order_id)
    assert order.status is OrderStatus.CANCELLED
    assert order.saga_step is OrderSagaStep.COMPENSATED
    assert len(order.lines) == 2
    assert await _outbox_rows(saga_session_factory, checkout.order_id) == []
    lines = await _cart_lines(saga_session_factory, checkout.user_id)
    assert {
        product_id: (line.quantity, line.unavailable_reason)
        for product_id, line in lines.items()
    } == {
        checkout.confirmed.product_id: (checkout.confirmed.quantity, None),
        checkout.unavailable.product_id: (checkout.unavailable.quantity, None),
    }
    assert all(line.locked_by_order_id is None for line in lines.values())
    assert await _journal(saga_session_factory, checkout.order_id) == [
        ("awaiting_reservation", "pending"),
        ("awaiting_reservation", "cancelled"),
        ("compensated", "cancelled"),
    ]


async def test_late_authorization_after_cancel_is_voided_once(
    saga_session_factory: async_sessionmaker[AsyncSession],
) -> None:
    checkout = await _checked_out_order(saga_session_factory)
    await _deliver_reserved(saga_session_factory, checkout, message_id=1)
    await _cancel(saga_session_factory, checkout)
    late_authorization_id = uuid.uuid4()

    # Авторизация ПОСЛЕ отмены; повтор того же факта с другим message_id.
    for message_id in (1, 2):
        await _deliver_authorization(
            saga_session_factory,
            checkout.order_id,
            "payment.authorized.v1",
            message_id=message_id,
            authorization_id=late_authorization_id,
        )

    order = await _load_order(saga_session_factory, checkout.order_id)
    assert order.status is OrderStatus.CANCELLED
    assert order.saga_step is OrderSagaStep.COMPENSATING
    assert order.payment_authorization_id == late_authorization_id
    rows = await _outbox_rows(saga_session_factory, checkout.order_id)
    assert _payloads(rows, "payment.void.v1") == [
        {"authorization_id": str(late_authorization_id)}
    ]
    assert _rows_of_type(rows, "inventory.allocate.v1") == []
    assert len(_rows_of_type(rows, "inventory.release.v1")) == 1


async def test_cancel_after_allocation_conflicts_and_changes_nothing(
    saga_session_factory: async_sessionmaker[AsyncSession],
) -> None:
    # Allocation ДО отмены: Saga уже запросила capture.
    checkout = await _allocated_order(saga_session_factory, uuid.uuid4())
    rows_before = await _outbox_rows(saga_session_factory, checkout.order_id)
    journal_before = await _journal(saga_session_factory, checkout.order_id)

    result = await _cancel(saga_session_factory, checkout)

    assert result.is_err
    assert result.error.code == "order_not_cancellable"
    order = await _load_order(saga_session_factory, checkout.order_id)
    assert order.status is OrderStatus.PENDING
    assert order.saga_step is OrderSagaStep.AWAITING_CAPTURE
    rows_after = await _outbox_rows(saga_session_factory, checkout.order_id)
    assert len(rows_after) == len(rows_before)
    assert await _journal(saga_session_factory, checkout.order_id) == journal_before


async def test_repeated_cancel_adds_no_command_or_history(
    saga_session_factory: async_sessionmaker[AsyncSession],
) -> None:
    checkout = await _authorized_order(saga_session_factory, uuid.uuid4())
    await _cancel(saga_session_factory, checkout)
    rows_before = await _outbox_rows(saga_session_factory, checkout.order_id)
    journal_before = await _journal(saga_session_factory, checkout.order_id)

    result = await _cancel(saga_session_factory, checkout)

    assert result.is_ok
    assert result.value.status == "cancelled"
    rows_after = await _outbox_rows(saga_session_factory, checkout.order_id)
    assert len(rows_after) == len(rows_before)
    assert await _journal(saga_session_factory, checkout.order_id) == journal_before


async def test_voided_fact_is_acknowledged_without_changes(
    saga_session_factory: async_sessionmaker[AsyncSession],
) -> None:
    authorization_id = uuid.uuid4()
    checkout = await _authorized_order(saga_session_factory, authorization_id)
    await _cancel(saga_session_factory, checkout)
    journal_before = await _journal(saga_session_factory, checkout.order_id)

    # Первая доставка захватывает inbox-ключ, повторная — пропускается.
    for message_id in (5, 5):
        await _deliver_voided(
            saga_session_factory,
            checkout.order_id,
            authorization_id=authorization_id,
            message_id=message_id,
        )

    async with saga_session_factory() as session:
        claimed = (
            await session.scalars(
                select(ProcessedMessageModel.message_id).where(
                    ProcessedMessageModel.source == "payment",
                    ProcessedMessageModel.message_id == 5,
                )
            )
        ).all()
    assert claimed == [5]
    order = await _load_order(saga_session_factory, checkout.order_id)
    assert order.saga_step is OrderSagaStep.COMPENSATING
    assert await _journal(saga_session_factory, checkout.order_id) == journal_before


async def test_expiry_before_a_late_reservation_result_expires_the_pending_order(
    saga_session_factory: async_sessionmaker[AsyncSession],
) -> None:
    checkout = await _checked_out_order(saga_session_factory)

    # Тот же случай, что для отменённого Order: истечение резерва обгоняет его
    # результат, inventory уже освободил резерв.
    await _deliver_released(
        saga_session_factory, checkout.order_id, message_id=2, reason="expired"
    )

    order = await _load_order(saga_session_factory, checkout.order_id)
    assert order.status is OrderStatus.EXPIRED
    assert order.failure_reason == "RESERVATION_EXPIRED"
    assert order.saga_step is OrderSagaStep.COMPENSATED
    lines = await _cart_lines(saga_session_factory, checkout.user_id)
    assert all(line.locked_by_order_id is None for line in lines.values())
    assert all(line.unavailable_reason is None for line in lines.values())

    # Поздний результат резерва и повтор истечения — no-op.
    await _deliver_reserved(saga_session_factory, checkout, message_id=1)
    await _deliver_released(
        saga_session_factory, checkout.order_id, message_id=3, reason="expired"
    )

    order = await _load_order(saga_session_factory, checkout.order_id)
    assert order.status is OrderStatus.EXPIRED
    assert order.saga_step is OrderSagaStep.COMPENSATED
    assert len(order.lines) == 2
    assert await _outbox_rows(saga_session_factory, checkout.order_id) == []


async def test_expiry_awaiting_authorization_expires_and_returns_lines(
    saga_session_factory: async_sessionmaker[AsyncSession],
) -> None:
    checkout = await _checked_out_order(saga_session_factory)
    await _deliver_reserved(saga_session_factory, checkout, message_id=1)

    await _deliver_released(
        saga_session_factory, checkout.order_id, message_id=2, reason="expired"
    )

    order = await _load_order(saga_session_factory, checkout.order_id)
    assert order.status is OrderStatus.EXPIRED
    assert order.failure_reason == "RESERVATION_EXPIRED"
    assert order.saga_step is OrderSagaStep.COMPENSATED
    assert OrderView.from_domain(order).status == "expired"
    assert (await _journal(saga_session_factory, checkout.order_id))[-1] == (
        "compensated",
        "expired",
    )
    rows = await _outbox_rows(saga_session_factory, checkout.order_id)
    assert [row.command_type for row in rows] == ["payment.authorize.v1"]
    lines = await _cart_lines(saga_session_factory, checkout.user_id)
    returned = lines[checkout.confirmed.product_id]
    assert returned.quantity == checkout.confirmed.quantity
    assert returned.unavailable_reason == "RESERVATION_EXPIRED"
    assert returned.locked_by_order_id is None

    # Поздняя авторизация истёкшего Order аннулируется.
    late_authorization_id = uuid.uuid4()
    await _deliver_authorization(
        saga_session_factory,
        checkout.order_id,
        "payment.authorized.v1",
        message_id=1,
        authorization_id=late_authorization_id,
    )

    rows = await _outbox_rows(saga_session_factory, checkout.order_id)
    assert _payloads(rows, "payment.void.v1") == [
        {"authorization_id": str(late_authorization_id)}
    ]
    assert _rows_of_type(rows, "inventory.allocate.v1") == []


async def test_expiry_awaiting_allocation_voids_the_stored_authorization(
    saga_session_factory: async_sessionmaker[AsyncSession],
) -> None:
    authorization_id = uuid.uuid4()
    checkout = await _authorized_order(saga_session_factory, authorization_id)

    await _deliver_released(
        saga_session_factory, checkout.order_id, message_id=2, reason="expired"
    )

    order = await _load_order(saga_session_factory, checkout.order_id)
    assert order.status is OrderStatus.EXPIRED
    assert order.saga_step is OrderSagaStep.COMPENSATED
    rows = await _outbox_rows(saga_session_factory, checkout.order_id)
    assert _payloads(rows, "payment.void.v1") == [
        {"authorization_id": str(authorization_id)}
    ]
    assert _rows_of_type(rows, "inventory.release.v1") == []
    lines = await _cart_lines(saga_session_factory, checkout.user_id)
    assert lines[checkout.confirmed.product_id].unavailable_reason == (
        "RESERVATION_EXPIRED"
    )


async def test_repeated_expiry_neither_doubles_lines_nor_voids_twice(
    saga_session_factory: async_sessionmaker[AsyncSession],
) -> None:
    checkout = await _authorized_order(saga_session_factory, uuid.uuid4())
    await _deliver_released(
        saga_session_factory, checkout.order_id, message_id=2, reason="expired"
    )
    journal_before = await _journal(saga_session_factory, checkout.order_id)

    # Та же доставка (тот же message_id) и тот же факт с другим message_id.
    for message_id in (2, 3):
        await _deliver_released(
            saga_session_factory,
            checkout.order_id,
            message_id=message_id,
            reason="expired",
        )

    rows = await _outbox_rows(saga_session_factory, checkout.order_id)
    assert len(_rows_of_type(rows, "payment.void.v1")) == 1
    assert await _journal(saga_session_factory, checkout.order_id) == journal_before
    lines = await _cart_lines(saga_session_factory, checkout.user_id)
    assert lines[checkout.confirmed.product_id].quantity == checkout.confirmed.quantity


async def test_expiry_after_capture_was_requested_changes_nothing(
    saga_session_factory: async_sessionmaker[AsyncSession],
) -> None:
    checkout = await _allocated_order(saga_session_factory, uuid.uuid4())
    rows_before = await _outbox_rows(saga_session_factory, checkout.order_id)
    journal_before = await _journal(saga_session_factory, checkout.order_id)

    await _deliver_released(
        saga_session_factory, checkout.order_id, message_id=3, reason="expired"
    )

    order = await _load_order(saga_session_factory, checkout.order_id)
    assert order.status is OrderStatus.PENDING
    assert order.saga_step is OrderSagaStep.AWAITING_CAPTURE
    rows_after = await _outbox_rows(saga_session_factory, checkout.order_id)
    assert len(rows_after) == len(rows_before)
    assert await _journal(saga_session_factory, checkout.order_id) == journal_before


async def test_cancel_after_expiry_conflicts(
    saga_session_factory: async_sessionmaker[AsyncSession],
) -> None:
    checkout = await _checked_out_order(saga_session_factory)
    await _deliver_reserved(saga_session_factory, checkout, message_id=1)
    await _deliver_released(
        saga_session_factory, checkout.order_id, message_id=2, reason="expired"
    )

    result = await _cancel(saga_session_factory, checkout)

    assert result.is_err
    assert result.error.code == "order_not_cancellable"
    order = await _load_order(saga_session_factory, checkout.order_id)
    assert order.status is OrderStatus.EXPIRED
