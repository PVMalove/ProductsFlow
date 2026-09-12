"""AC1 (архитектурный бриф, Risks №4): конкурентные `reserve()` на один
`product_id` через ДВЕ независимые сессии/соединения — не через AMQP
(`consume_command`'s `prefetch_count=1` сериализовал бы очередь и ничего не
доказал бы про `SELECT ... FOR UPDATE`). Мирует #369's
`test_get_or_create_concurrent_calls_create_exactly_one_cart_row` (issue
#370, Seams for TDD #8): собственный `sessionmaker` на корутину -> собственное
реальное соединение/транзакция из пула, не общий savepoint-`db_session`."""

import asyncio
import uuid

import pytest
from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncEngine, async_sessionmaker

from infrastructure.db.entity_configurations.models import InventoryModel
from infrastructure.db.inventory_repository import InventoryRepository

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
