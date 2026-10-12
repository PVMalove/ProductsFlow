"""OrderRepository/IdempotencyKeyRepository/SagaCommandOutboxRepository
round-trip against real Postgres (issue #372, Seams for TDD #9; issue #376 —
Saga transition journal and drained `order.completed.v1`). The
migration/diff coverage itself lives in test_cart_repository.py's full
history round-trip test."""

import uuid
from datetime import UTC, datetime

import pytest
from kernel_platform.outbox.models import OutboxMessage
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from domain.entities.idempotency_key import IdempotencyKeyRecord
from domain.entities.order import (
    AuthorizationOutcome,
    Order,
    OrderLine,
    OrderSagaStep,
    OrderStatus,
)
from infrastructure.db.entity_configurations.models import (
    OrderSagaTransitionModel,
    ReservationOutboxModel,
)
from infrastructure.db.idempotency_key_repository import IdempotencyKeyRepository
from infrastructure.db.order_repository import OrderRepository
from infrastructure.db.saga_command_outbox_repository import (
    SagaCommandOutboxRepository,
)

pytestmark = pytest.mark.asyncio(loop_scope="session")


def _order_with_two_lines() -> Order:
    lines = [
        OrderLine(
            id=uuid.uuid4(), product_id=uuid.uuid4(), quantity=1, unit_price_kopecks=100
        ),
        OrderLine(
            id=uuid.uuid4(), product_id=uuid.uuid4(), quantity=2, unit_price_kopecks=200
        ),
    ]
    return Order.create(uuid.uuid4(), user_id=uuid.uuid4(), lines=lines)


async def test_order_save_and_get_by_id_round_trips(db_session: AsyncSession) -> None:
    repo = OrderRepository(db_session)
    order = _order_with_two_lines()

    await repo.save(order)
    await db_session.flush()

    fetched = await repo.get_by_id(order.id)
    assert fetched is not None
    assert fetched.user_id == order.user_id
    assert fetched.status is OrderStatus.PENDING
    assert fetched.saga_step is OrderSagaStep.AWAITING_RESERVATION
    assert {line.product_id for line in fetched.lines} == {
        line.product_id for line in order.lines
    }


async def test_order_save_trims_lines_on_partial_reservation(
    db_session: AsyncSession,
) -> None:
    repo = OrderRepository(db_session)
    order = _order_with_two_lines()
    confirmed_product_id = order.lines[0].product_id
    await repo.save(order)
    await db_session.flush()

    order.apply_reservation_result(
        confirmed_product_ids=frozenset({confirmed_product_id})
    )
    await repo.save(order)
    await db_session.flush()

    fetched = await repo.get_by_id(order.id)
    assert fetched is not None
    assert len(fetched.lines) == 1
    assert fetched.lines[0].product_id == confirmed_product_id
    assert fetched.saga_step is OrderSagaStep.AWAITING_AUTHORIZATION


async def test_order_save_persists_payment_authorization_id(
    db_session: AsyncSession,
) -> None:
    repo = OrderRepository(db_session)
    order = _order_with_two_lines()
    await repo.save(order)
    await db_session.flush()
    order.apply_reservation_result(
        confirmed_product_ids=frozenset({order.lines[0].product_id})
    )
    authorization_id = uuid.uuid4()
    order.apply_authorization_result(
        outcome=AuthorizationOutcome.AUTHORIZED, authorization_id=authorization_id
    )

    await repo.save(order)
    await db_session.flush()

    fetched = await repo.get_by_id(order.id)
    assert fetched is not None
    assert fetched.status is OrderStatus.PENDING
    assert fetched.saga_step is OrderSagaStep.AWAITING_ALLOCATION
    assert fetched.payment_authorization_id == authorization_id


async def _journal(session: AsyncSession, order_id: uuid.UUID) -> list[tuple[str, str]]:
    rows = (
        await session.scalars(
            select(OrderSagaTransitionModel)
            .where(OrderSagaTransitionModel.order_id == order_id)
            .order_by(OrderSagaTransitionModel.id)
        )
    ).all()
    return [(row.saga_step, row.status) for row in rows]


async def test_order_save_journals_the_initial_step_on_insert(
    db_session: AsyncSession,
) -> None:
    repo = OrderRepository(db_session)
    order = _order_with_two_lines()

    await repo.save(order)
    await db_session.flush()

    assert await _journal(db_session, order.id) == [("awaiting_reservation", "pending")]


async def test_order_save_journals_each_step_or_status_change(
    db_session: AsyncSession,
) -> None:
    repo = OrderRepository(db_session)
    order = _order_with_two_lines()
    await repo.save(order)
    await db_session.flush()

    order.apply_reservation_result(
        confirmed_product_ids=frozenset({order.lines[0].product_id})
    )
    await repo.save(order)
    await db_session.flush()
    order.apply_authorization_result(
        outcome=AuthorizationOutcome.DECLINED, authorization_id=uuid.uuid4()
    )
    await repo.save(order)
    await db_session.flush()

    assert await _journal(db_session, order.id) == [
        ("awaiting_reservation", "pending"),
        ("awaiting_authorization", "pending"),
        ("compensating", "failed"),
    ]


async def test_order_save_without_a_step_or_status_change_journals_nothing(
    db_session: AsyncSession,
) -> None:
    repo = OrderRepository(db_session)
    order = _order_with_two_lines()
    await repo.save(order)
    await db_session.flush()

    await repo.save(order)
    await db_session.flush()

    assert await _journal(db_session, order.id) == [("awaiting_reservation", "pending")]


async def _outbox_messages(
    session: AsyncSession, order_id: uuid.UUID
) -> list[OutboxMessage]:
    return list(
        (
            await session.scalars(
                select(OutboxMessage).where(OutboxMessage.aggregate_id == order_id)
            )
        ).all()
    )


async def test_order_save_drains_order_completed_into_outbox_messages(
    db_session: AsyncSession,
) -> None:
    repo = OrderRepository(db_session)
    order = _order_with_two_lines()
    await repo.save(order)
    await db_session.flush()
    order.apply_reservation_result(
        confirmed_product_ids=frozenset(line.product_id for line in order.lines)
    )
    authorization_id = uuid.uuid4()
    order.apply_authorization_result(
        outcome=AuthorizationOutcome.AUTHORIZED, authorization_id=authorization_id
    )
    order.apply_allocation_result()
    causation_id = uuid.uuid4()
    order.apply_capture_result(
        authorization_id=authorization_id, causation_id=causation_id
    )

    await repo.save(order)
    await db_session.flush()

    rows = await _outbox_messages(db_session, order.id)
    assert len(rows) == 1
    row = rows[0]
    assert row.event_type == "order.completed.v1"
    assert row.aggregate_type == "Order"
    assert row.published_at is None
    assert row.payload == {
        "order_id": str(order.id),
        "correlation_id": str(order.id),
        "causation_id": str(causation_id),
    }
    assert await _journal(db_session, order.id) == [
        ("awaiting_reservation", "pending"),
        ("captured", "completed"),
    ]
    fetched = await repo.get_by_id(order.id)
    assert fetched is not None
    assert fetched.status is OrderStatus.COMPLETED
    assert fetched.saga_step is OrderSagaStep.CAPTURED


async def test_order_save_without_domain_events_writes_no_outbox_message(
    db_session: AsyncSession,
) -> None:
    repo = OrderRepository(db_session)
    order = _order_with_two_lines()

    await repo.save(order)
    await db_session.flush()

    assert await _outbox_messages(db_session, order.id) == []


async def test_order_get_by_id_returns_none_for_unknown_order(
    db_session: AsyncSession,
) -> None:
    repo = OrderRepository(db_session)

    fetched = await repo.get_by_id(uuid.uuid4())

    assert fetched is None


async def test_idempotency_key_save_and_get_round_trips(
    db_session: AsyncSession,
) -> None:
    repo = IdempotencyKeyRepository(db_session)
    record = IdempotencyKeyRecord(
        user_id=uuid.uuid4(),
        key="checkout-key-1",
        request_fingerprint="fingerprint-1",
        order_id=uuid.uuid4(),
        created_at=datetime.now(UTC),
    )

    await repo.save(record)
    await db_session.flush()

    fetched = await repo.get(record.user_id, record.key)
    assert fetched is not None
    assert fetched.request_fingerprint == "fingerprint-1"
    assert fetched.order_id == record.order_id


async def test_idempotency_key_get_returns_none_when_absent(
    db_session: AsyncSession,
) -> None:
    repo = IdempotencyKeyRepository(db_session)

    fetched = await repo.get(uuid.uuid4(), "unknown-key")

    assert fetched is None


async def test_reservation_outbox_enqueue_persists_an_unpublished_row(
    db_session: AsyncSession,
) -> None:
    repo = SagaCommandOutboxRepository(db_session)
    order_id = uuid.uuid4()
    lines = [
        OrderLine(
            id=uuid.uuid4(), product_id=uuid.uuid4(), quantity=3, unit_price_kopecks=500
        )
    ]

    await repo.enqueue(order_id=order_id, lines=lines)
    await db_session.flush()

    row = await db_session.scalar(
        select(ReservationOutboxModel).where(
            ReservationOutboxModel.order_id == order_id
        )
    )
    assert row is not None
    assert row.published_at is None
    assert row.command_type == "inventory.reserve.v1"
    assert row.payload["order_id"] == str(order_id)
    assert row.payload["lines"] == [
        {"product_id": str(lines[0].product_id), "quantity": 3}
    ]


async def test_reservation_outbox_enqueue_authorization_persists_payment_command(
    db_session: AsyncSession,
) -> None:
    repo = SagaCommandOutboxRepository(db_session)
    order_id = uuid.uuid4()

    await repo.enqueue_authorization(
        order_id=order_id, amount_kopecks=4_200, payment_method_token="success"
    )
    await db_session.flush()

    row = await db_session.scalar(
        select(ReservationOutboxModel).where(
            ReservationOutboxModel.order_id == order_id
        )
    )
    assert row is not None
    assert row.published_at is None
    assert row.command_type == "payment.authorize.v1"
    assert row.payload == {"amount": 4_200, "payment_method_token": "success"}


async def test_reservation_outbox_enqueue_release_persists_inventory_command(
    db_session: AsyncSession,
) -> None:
    repo = SagaCommandOutboxRepository(db_session)
    order_id = uuid.uuid4()

    await repo.enqueue_release(order_id=order_id)
    await db_session.flush()

    row = await db_session.scalar(
        select(ReservationOutboxModel).where(
            ReservationOutboxModel.order_id == order_id
        )
    )
    assert row is not None
    assert row.command_type == "inventory.release.v1"
    assert row.payload == {"order_id": str(order_id)}
