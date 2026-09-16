"""OrderRepository/IdempotencyKeyRepository/ReservationOutboxRepository
round-trip against real Postgres (issue #372, Seams for TDD #9). The
migration/diff coverage itself lives in test_cart_repository.py's full
history round-trip test."""

import uuid
from datetime import UTC, datetime

import pytest
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from domain.entities.idempotency_key import IdempotencyKeyRecord
from domain.entities.order import Order, OrderLine, OrderSagaStep, OrderStatus
from infrastructure.db.entity_configurations.models import ReservationOutboxModel
from infrastructure.db.idempotency_key_repository import IdempotencyKeyRepository
from infrastructure.db.order_repository import OrderRepository
from infrastructure.db.reservation_outbox_repository import (
    ReservationOutboxRepository,
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
    assert fetched.saga_step is OrderSagaStep.RESERVATION_CONFIRMED


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
    repo = ReservationOutboxRepository(db_session)
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
    assert row.payload["order_id"] == str(order_id)
    assert row.payload["lines"] == [
        {"product_id": str(lines[0].product_id), "quantity": 3}
    ]
