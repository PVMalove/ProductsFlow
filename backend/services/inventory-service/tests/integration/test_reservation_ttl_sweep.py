# ruff: noqa: E501
"""TTL-sweep (issue #370, D6, Seams for TDD #10) — фиксированный `now`, без
реального `sleep` 15 минут (мирует #369's `Cart.add_line(..., now: datetime)`
тестируемость): истёкший `ACTIVE`-резерв освобождается за один sweep-проход
(`run_once`), помечается `EXPIRED`, создаёт `inventory.released.v1`
(reason="expired") в outbox; НЕ истёкший резерв в том же проходе не тронут."""

import uuid
from datetime import UTC, datetime, timedelta

import pytest
import pytest_asyncio
from kernel_platform.outbox.models import OutboxMessage
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncEngine, AsyncSession, async_sessionmaker

from api.reservation_sweep import run_once
from domain.entities.reservation import (
    Reservation,
    ReservationLine,
    ReservationLineStatus,
)
from domain.reservation_status import ReservationStatus
from infrastructure.db.entity_configurations.models import (
    InventoryModel,
    ReservationModel,
)
from infrastructure.db.reservation_repository import ReservationRepository

pytestmark = pytest.mark.asyncio(loop_scope="session")


@pytest_asyncio.fixture
async def sweep_session_factory(
    db_engine: AsyncEngine,
) -> async_sessionmaker[AsyncSession]:
    return async_sessionmaker(db_engine, expire_on_commit=False)


async def test_run_once_releases_only_expired_active_reservations(
    sweep_session_factory: async_sessionmaker[AsyncSession],
) -> None:
    now = datetime(2026, 9, 12, 12, 0, tzinfo=UTC)
    expired_product_id = uuid.uuid4()
    not_expired_product_id = uuid.uuid4()
    expired_order_id = uuid.uuid4()
    not_expired_order_id = uuid.uuid4()

    async with sweep_session_factory() as session:
        session.add(
            InventoryModel(product_id=expired_product_id, quantity=10, reserved=4)
        )
        session.add(
            InventoryModel(product_id=not_expired_product_id, quantity=10, reserved=3)
        )
        await session.commit()

    async with sweep_session_factory() as session:
        reservation_repo = ReservationRepository(session)
        expired = Reservation.create(
            expired_order_id,
            lines=[
                ReservationLine(
                    id=uuid.uuid4(),
                    product_id=expired_product_id,
                    quantity=4,
                    status=ReservationLineStatus.CONFIRMED,
                )
            ],
            ttl_minutes=15,
            now=now - timedelta(minutes=30),
        )
        not_expired = Reservation.create(
            not_expired_order_id,
            lines=[
                ReservationLine(
                    id=uuid.uuid4(),
                    product_id=not_expired_product_id,
                    quantity=3,
                    status=ReservationLineStatus.CONFIRMED,
                )
            ],
            ttl_minutes=15,
            now=now,
        )
        await reservation_repo.try_create(expired)
        await reservation_repo.try_create(not_expired)
        await session.commit()

    released_count = await run_once(sweep_session_factory, now=now)

    assert released_count == 1

    async with sweep_session_factory() as session:
        expired_reservation = await session.get(ReservationModel, expired_order_id)
        not_expired_reservation = await session.get(
            ReservationModel, not_expired_order_id
        )
        expired_inventory_reserved = await session.scalar(
            select(InventoryModel.reserved).where(
                InventoryModel.product_id == expired_product_id
            )
        )
        not_expired_inventory_reserved = await session.scalar(
            select(InventoryModel.reserved).where(
                InventoryModel.product_id == not_expired_product_id
            )
        )
        released_outbox_count = await session.scalar(
            select(func.count())
            .select_from(OutboxMessage)
            .where(
                OutboxMessage.event_type == "inventory.released.v1",
                OutboxMessage.aggregate_id == expired_order_id,
            )
        )

    assert expired_reservation is not None
    assert expired_reservation.status == ReservationStatus.EXPIRED.value
    assert not_expired_reservation is not None
    assert not_expired_reservation.status == ReservationStatus.ACTIVE.value
    assert expired_inventory_reserved == 0
    assert not_expired_inventory_reserved == 3
    assert released_outbox_count == 1


async def test_run_once_is_a_noop_when_nothing_is_expired(
    sweep_session_factory: async_sessionmaker[AsyncSession],
) -> None:
    now = datetime(2026, 9, 12, 12, 0, tzinfo=UTC)

    released_count = await run_once(sweep_session_factory, now=now)

    assert released_count == 0
