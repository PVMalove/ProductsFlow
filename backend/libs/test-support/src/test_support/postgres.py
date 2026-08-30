"""Postgres-testcontainers-фикстуры, переиспользуемые сервисами backend/ (ADR 0018).

Подключаются как pytest-плагин из top-level conftest.py сервиса (pytest
требует объявлять `pytest_plugins` там, а не во вложенном conftest.py —
см. https://docs.pytest.org/en/stable/deprecations.html#pytest-plugins-in-non-top-level-conftest-files)::

    pytest_plugins = ["test_support.postgres"]

`postgres_dbname` — точка параметризации по имени БД вызывающего сервиса:
переопределяется одноимённой фикстурой в conftest.py сервиса, если дефолтное
имя "test" не подходит. Миграции модуль не запускает — у каждого сервиса своя
alembic-история/своё `Base.metadata`, это остаётся на стороне вызывающего
conftest.py (тот же приём, что уже применяют identity-service и
kernel-platform в своих локальных заглушках, ADR 0018 issue #99).
"""

from collections.abc import AsyncIterator, Iterator

import pytest
import pytest_asyncio
from sqlalchemy.ext.asyncio import AsyncEngine, AsyncSession, create_async_engine
from testcontainers.community.postgres import PostgresContainer

POSTGRES_IMAGE = "postgres:18.0"


@pytest.fixture(scope="session")
def postgres_dbname() -> str:
    return "test"


@pytest.fixture(scope="session")
def postgres_container(postgres_dbname: str) -> Iterator[PostgresContainer]:
    with PostgresContainer(
        POSTGRES_IMAGE, dbname=postgres_dbname, driver="asyncpg"
    ) as container:
        yield container


@pytest_asyncio.fixture(scope="session", loop_scope="session")
async def db_engine(
    postgres_container: PostgresContainer,
) -> AsyncIterator[AsyncEngine]:
    engine = create_async_engine(postgres_container.get_connection_url())
    try:
        yield engine
    finally:
        await engine.dispose()


@pytest_asyncio.fixture(loop_scope="session")
async def db_session(db_engine: AsyncEngine) -> AsyncIterator[AsyncSession]:
    async with db_engine.connect() as connection:
        await connection.begin()
        session = AsyncSession(
            bind=connection, join_transaction_mode="create_savepoint"
        )
        try:
            yield session
        finally:
            await session.close()
            await connection.rollback()
