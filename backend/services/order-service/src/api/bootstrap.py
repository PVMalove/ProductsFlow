import asyncio
import logging

from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncEngine, create_async_engine

from core.settings import settings

logger = logging.getLogger(__name__)


async def check_database_connectivity(engine: AsyncEngine) -> None:
    """Проверяет, что БД принимает соединения; при отказе поднимает исключение.

    Выполняется после `alembic upgrade head` как последний шаг
    order-bootstrap (ADR 0001) — сида нет: order-service не сидирует
    демо-данные (issue #369)."""
    async with engine.connect() as connection:
        await connection.execute(text("SELECT 1"))


async def main() -> None:
    if not settings.order_database_url:
        raise RuntimeError("ORDER_DATABASE_URL must be configured")
    engine = create_async_engine(
        settings.order_database_url,
        pool_pre_ping=True,
        pool_size=settings.db_pool_size,
        max_overflow=settings.db_max_overflow,
        pool_recycle=settings.db_pool_recycle,
    )
    try:
        await check_database_connectivity(engine)
    finally:
        await engine.dispose()
    logger.info("order-bootstrap: database connectivity verified")


if __name__ == "__main__":
    asyncio.run(main())
