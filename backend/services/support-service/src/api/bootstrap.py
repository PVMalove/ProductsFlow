import asyncio
import logging

from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncEngine, create_async_engine

from core.settings import settings

logger = logging.getLogger(__name__)


async def check_database_connectivity(engine: AsyncEngine) -> None:
    """Проверяет, что БД принимает соединения; при отказе поднимает исключение.

    Выполняется после `alembic upgrade head` как последний шаг
    support-bootstrap (ADR 0001) — у support нет этапа bucket-ensure или сида.
    """
    async with engine.connect() as connection:
        await connection.execute(text("SELECT 1"))


async def main() -> None:
    if not settings.support_database_url:
        raise RuntimeError("SUPPORT_DATABASE_URL must be configured")
    engine = create_async_engine(settings.support_database_url)
    try:
        await check_database_connectivity(engine)
    finally:
        await engine.dispose()
    logger.info("support-bootstrap: database connectivity verified")


if __name__ == "__main__":
    asyncio.run(main())
