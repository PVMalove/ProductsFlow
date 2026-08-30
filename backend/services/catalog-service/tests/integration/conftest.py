from collections.abc import AsyncIterator

import pytest_asyncio
from kernel_platform.outbox.models import Base
from sqlalchemy.ext.asyncio import AsyncEngine

# Импорт регистрирует ProductModel/ProductAuditLog на общем Base.metadata
# (тот же Base, что и kernel_platform.OutboxMessage) — сам модуль напрямую
# не используется, только его сторонний эффект на импорте.
from catalog.infrastructure import db as _db  # noqa: F401


@pytest_asyncio.fixture(scope="session", loop_scope="session", autouse=True)
async def _schema(db_engine: AsyncEngine) -> AsyncIterator[None]:
    """test_support.postgres не запускает миграции (у каждого сервиса своя
    alembic-история) — здесь создаём схему напрямую из ORM-метаданных, тем
    же приёмом, что уже применяет identity-service (tests/integration/
    test_outbox_publisher.py::_outbox_table)."""
    async with db_engine.begin() as connection:
        await connection.run_sync(Base.metadata.create_all)
    try:
        yield
    finally:
        async with db_engine.begin() as connection:
            await connection.run_sync(Base.metadata.drop_all)
