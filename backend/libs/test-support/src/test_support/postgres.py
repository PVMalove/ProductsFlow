# ruff: noqa: E501
"""Postgres-testcontainers-фикстуры, переиспользуемые сервисами backend/ .

Подключаются как pytest-плагин из top-level conftest.py сервиса (pytest
требует объявлять `pytest_plugins` там, а не во вложенном conftest.py —
см. https://docs.pytest.org/en/stable/deprecations.html#pytest-plugins-in-non-top-level-conftest-files)::

    pytest_plugins = ["test_support.postgres"]

`postgres_dbname`/`postgres_schema` — точки параметризации по имени БД/схеме
вызывающего сервиса: переопределяются одноимёнными фикстурами в conftest.py
сервиса, если дефолты ("test" / `None` → "public") не подходят. Миграции
модуль не запускает — у каждого сервиса своя alembic-история/своё
`Base.metadata`, это остаётся на стороне вызывающего conftest.py (тот же
приём, что уже применяют identity-service и kernel-platform в своих
локальных заглушках,  issue #99).
"""

from collections.abc import AsyncIterator, Iterator

import pytest
import pytest_asyncio
from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncEngine, AsyncSession, create_async_engine
from testcontainers.community.postgres import PostgresContainer

POSTGRES_IMAGE = "postgres:18.0"


@pytest.fixture(scope="session")
def postgres_dbname() -> str:
    """Возвращает дефолтное имя БД для Postgres в тестконтейнере.

    Используется как точка переопределения (override) в сервисах через conftest.py.

    Returns:
        str: Имя БД ("test")."""
    return "test"


@pytest.fixture(scope="session")
def postgres_schema() -> str | None:
    """Определяет целевую схему в Postgres для тестов.

    Используется как точка переопределения. Если `None`, драйвер будет юзать дефолтную `public`.

    Returns:
        str | None: Название схемы или `None`."""
    return None


@pytest.fixture(scope="session")
def postgres_container(postgres_dbname: str) -> Iterator[PostgresContainer]:
    """Поднимает Docker-контейнер с Postgres.

    Флоу:
    Использует `testcontainers`. Блокирует старт тестов, пока база не ответит на пинг (wait_for_connection под капотом).
    Скоуп `session` гарантирует, что контейнер поднимается ровно один раз за прогон.

    Args:
        postgres_dbname (str): Название базы (из фикстуры).

    Yields:
        PostgresContainer: Инстанс запущенного контейнера, который прибивается на выходе."""
    with PostgresContainer(
        POSTGRES_IMAGE, dbname=postgres_dbname, driver="asyncpg"
    ) as container:
        yield container


@pytest_asyncio.fixture(scope="session", loop_scope="session")
async def db_engine(
    postgres_container: PostgresContainer, postgres_schema: str | None
) -> AsyncIterator[AsyncEngine]:
    """Инициализирует асинхронный SQLAlchemy engine (пул коннектов) к тестконтейнеру.

    Алгоритм:
    1. Забирает урл подключения у контейнера.
    2. Если задана кастомная схема (`postgres_schema`), инжектит `search_path` в параметры коннекта (`asyncpg`).
    3. При наличии схемы делает DDL `CREATE SCHEMA IF NOT EXISTS`, чтобы подготовить плацдарм перед миграциями.
    4. Выплевывает engine, по завершении тестов делает `dispose()` пула.

    Args:
        postgres_container (PostgresContainer): Работающий контейнер.
        postgres_schema (str | None): Опциональная схема.

    Yields:
        AsyncEngine: Готовый к бою алхимовский движок."""
    connect_args = (
        {"server_settings": {"search_path": postgres_schema}} if postgres_schema else {}
    )
    engine = create_async_engine(
        postgres_container.get_connection_url(), connect_args=connect_args
    )
    if postgres_schema:
        async with engine.begin() as connection:
            await connection.execute(
                text(f'CREATE SCHEMA IF NOT EXISTS "{postgres_schema}"')
            )
    try:
        yield engine
    finally:
        await engine.dispose()


@pytest_asyncio.fixture(loop_scope="session")
async def db_session(db_engine: AsyncEngine) -> AsyncIterator[AsyncSession]:
    """Выдает транзакционную асинхронную сессию SQLAlchemy для конкретного теста.

    Хак с транзакциями:
    Сессия стартует внутри уже открытой транзакции (`connection.begin()`), а сам `AsyncSession` настраивается на `join_transaction_mode="create_savepoint"`.
    Это классический паттерн "вложенных транзакций": каждый `session.commit()` в бизнес-коде делает только `RELEASE SAVEPOINT`, а в `finally` фикстуры происходит жесткий `rollback()`.
    В итоге после каждого теста база кристально чистая, и тесты не аффектят друг друга.

    Args:
        db_engine (AsyncEngine): Инстанс движка.

    Yields:
        AsyncSession: Асинхронная сессия."""
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
