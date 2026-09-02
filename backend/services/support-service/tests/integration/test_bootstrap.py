import pytest
from sqlalchemy.ext.asyncio import AsyncEngine, create_async_engine

from api.bootstrap import check_database_connectivity

pytestmark = pytest.mark.asyncio(loop_scope="session")


async def test_check_database_connectivity_succeeds_against_live_database(
    db_engine: AsyncEngine,
) -> None:
    await check_database_connectivity(db_engine)


async def test_check_database_connectivity_raises_when_database_unreachable() -> None:
    unreachable_engine = create_async_engine(
        "postgresql+asyncpg://admin:admin@127.0.0.1:1/nonexistent"
    )
    try:
        with pytest.raises(Exception):  # noqa: B017 — driver-specific connection error
            await check_database_connectivity(unreachable_engine)
    finally:
        await unreachable_engine.dispose()
