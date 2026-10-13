"""AC1 (архитектурный бриф, Risks №4): конкурентные `reserve()` на один
`product_id` через ДВЕ независимые сессии/соединения — не через AMQP
(`consume_command`'s `prefetch_count=1` сериализовал бы очередь и ничего не
доказал бы про `SELECT ... FOR UPDATE`). Мирует #369's
`test_get_or_create_concurrent_calls_create_exactly_one_cart_row` (issue
#370, Seams for TDD #8): собственный `sessionmaker` на корутину -> собственное
реальное соединение/транзакция из пула, не общий savepoint-`db_session`."""

import asyncio
import uuid
from datetime import UTC, datetime, timedelta

import pytest
from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncEngine, async_sessionmaker

from application.commands.allocate_inventory_reservation import (
    AllocateInventoryReservationCommand,
    AllocateInventoryReservationCommandHandler,
)
from application.commands.release_inventory_reservation import (
    ReleaseInventoryReservationCommand,
    ReleaseInventoryReservationCommandHandler,
)
from infrastructure.db.entity_configurations.models import (
    InventoryModel,
    ReservationModel,
)
from infrastructure.db.inventory_repository import InventoryRepository
from infrastructure.db.reservation_repository import ReservationRepository

pytestmark = pytest.mark.asyncio(loop_scope="session")


async def test_concurrent_reserve_never_exceeds_available_quantity(
    db_engine: AsyncEngine,
) -> None:
    product_id = uuid.uuid4()
    sessionmaker = async_sessionmaker(db_engine, expire_on_commit=False)

    async with sessionmaker() as setup_session:
        setup_session.add(
            InventoryModel(product_id=product_id, quantity=10, reserved=0)
        )
        await setup_session.commit()

    async def _reserve(quantity: int) -> bool:
        async with sessionmaker() as session:
            repo = InventoryRepository(session)
            result = await repo.reserve(product_id, quantity)
            await session.commit()
            return result is not None and result.is_ok

    try:
        first, second = await asyncio.gather(_reserve(6), _reserve(6))

        # Сумма запрошенного (12) превышает available (10) — обе не могут
        # успеть одновременно, ровно одна должна быть отклонена.
        assert sorted([first, second]) == [False, True]

        async with db_engine.connect() as connection:
            reserved = await connection.scalar(
                text("SELECT reserved FROM inventory WHERE product_id = :product_id"),
                {"product_id": product_id},
            )
            assert reserved == 6
    finally:
        async with db_engine.begin() as connection:
            await connection.execute(
                text("DELETE FROM inventory WHERE product_id = :product_id"),
                {"product_id": product_id},
            )


async def test_allocate_does_not_lose_concurrent_ttl_sweep_expiry(
    db_engine: AsyncEngine,
) -> None:
    """Code-review finding (Spec axis, retry dispatch on #373): `allocate()`'s
    read of a reservation raced the TTL-sweep's `claim_expired()` without
    sharing its `FOR UPDATE` row-locking discipline — the sweep's EXPIRED
    write could be silently lost-updated back to ALLOCATED. Own sessionmaker
    per coroutine (mirrors the test above), plus an `asyncio.Event` to pin the
    interleaving deterministically: the sweep must acquire its row lock
    before allocate attempts its own read, otherwise `claim_expired`'s
    `SKIP LOCKED` would just skip the row instead of racing."""
    order_id = uuid.uuid4()
    sessionmaker = async_sessionmaker(db_engine, expire_on_commit=False)
    sweep_locked = asyncio.Event()

    async with sessionmaker() as setup_session:
        setup_session.add(
            ReservationModel(
                order_id=order_id,
                status="active",
                expires_at=datetime.now(UTC) - timedelta(minutes=1),
                created_at=datetime.now(UTC) - timedelta(minutes=5),
            )
        )
        await setup_session.commit()

    async def _ttl_sweep_expire() -> None:
        async with sessionmaker() as session:
            async with session.begin():
                repo = ReservationRepository(session)
                expired = await repo.claim_expired(now=datetime.now(UTC), limit=10)
                sweep_locked.set()
                # Расширяем окно гонки: allocate() успевает попытаться
                # прочитать/заблокировать ту же строку до commit sweep'а.
                await asyncio.sleep(0.2)
                handler = ReleaseInventoryReservationCommandHandler(
                    InventoryRepository(session), repo
                )
                for reservation in expired:
                    await handler.execute(
                        ReleaseInventoryReservationCommand(
                            order_id=reservation.id, reason="expired"
                        )
                    )

    async def _allocate() -> None:
        await sweep_locked.wait()
        async with sessionmaker() as session:
            async with session.begin():
                repo = ReservationRepository(session)
                handler = AllocateInventoryReservationCommandHandler(repo)
                await handler.execute(
                    AllocateInventoryReservationCommand(order_id=order_id)
                )

    try:
        await asyncio.gather(_ttl_sweep_expire(), _allocate())

        async with db_engine.connect() as connection:
            status = await connection.scalar(
                text("SELECT status FROM reservations WHERE order_id = :order_id"),
                {"order_id": order_id},
            )
            # Sweep взял блокировку первым — allocate() обязан увидеть уже
            # зафиксированный EXPIRED и стать no-op, а не молча перезаписать
            # его обратно в ALLOCATED (lost update).
            assert status == "expired"
    finally:
        async with db_engine.begin() as connection:
            await connection.execute(
                text("DELETE FROM reservations WHERE order_id = :order_id"),
                {"order_id": order_id},
            )
