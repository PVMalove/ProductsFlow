import asyncio
import logging

from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncEngine, create_async_engine

from core.settings import settings

logger = logging.getLogger(__name__)


async def check_database_connectivity(engine: AsyncEngine) -> None:
    """Verify the database accepts connections; raises on failure.

    Run after `alembic upgrade head` as the last step of support-bootstrap
    (ADR 0017) — support has no bucket-ensure or seed stage.
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
