"""Repository round-trip + Alembic-миграция (issue #367, Seams for TDD #7):
`alembic upgrade head` создаёт таблицу `inventory` с PK на `product_id`,
совпадающую с ORM-метаданными; `InventoryRepository` — CRUD round-trip."""

import uuid
from pathlib import Path
from runpy import run_path
from typing import Any

import pytest
from alembic.autogenerate import compare_metadata
from alembic.migration import MigrationContext
from alembic.operations import Operations
from sqlalchemy import Connection, inspect, text
from sqlalchemy.ext.asyncio import AsyncEngine, AsyncSession

from infrastructure.db import audit as _audit  # noqa: F401
from infrastructure.db.entity_configurations import models as _models
from infrastructure.db.inventory_repository import InventoryRepository

pytestmark = pytest.mark.asyncio(loop_scope="session")

_VERSIONS_DIR = Path(__file__).parents[2] / "src/infrastructure/db/alembic/versions"
_REVISION_FILE = "1106f353bbf1_inventory_domain_outbox.py"
_REVISION = run_path(str(_VERSIONS_DIR / _REVISION_FILE))
_TABLES = ("inventory", "inventory_audit_log", "outbox_messages", "processed_messages")


def _run_revision(connection: Connection, action: str) -> None:
    migration_context = MigrationContext.configure(connection)
    with Operations.context(migration_context):
        _REVISION[action]()


def _diff_against_orm_metadata(connection: Connection) -> list[Any]:
    migration_context = MigrationContext.configure(connection)
    return compare_metadata(migration_context, _models.Base.metadata)


def _inventory_primary_key_columns(connection: Connection) -> list[str]:
    return inspect(connection).get_pk_constraint("inventory")["constrained_columns"]


async def test_alembic_upgrade_creates_inventory_table_with_pk_and_downgrade_reverts(
    db_engine: AsyncEngine,
) -> None:
    # Гоняем upgrade/diff/downgrade внутри ОДНОЙ транзакции, откатываемой в
    # конце (rollback, не commit) — так этот тест не мутирует персистентное
    # состояние БД, которое видят другие интеграционные тесты в той же
    # session-scoped `_schema` (issue #367): без rollback здесь DROP TABLE
    # внутри upgrade() уничтожил бы таблицы, уже созданные ORM-метаданными
    # автосоздание-фикстурой conftest.py для всех остальных тестов сессии.
    async with db_engine.connect() as connection:
        await connection.begin()
        try:
            # `_schema` (tests/integration/conftest.py) уже создал эти
            # таблицы через `Base.metadata.create_all` — чистим их перед
            # прогоном самой Alembic-ревизии, иначе `create_table` упадёт на
            # "relation already exists".
            for table in _TABLES:
                await connection.execute(text(f"DROP TABLE IF EXISTS {table} CASCADE"))

            await connection.run_sync(lambda conn: _run_revision(conn, "upgrade"))

            pk_columns = await connection.run_sync(_inventory_primary_key_columns)
            assert pk_columns == ["product_id"]

            diffs = await connection.run_sync(_diff_against_orm_metadata)
            assert diffs == []

            await connection.run_sync(lambda conn: _run_revision(conn, "downgrade"))

            remaining_tables = await connection.scalar(
                text(
                    "SELECT count(*) FROM information_schema.tables "
                    "WHERE table_schema = 'public' AND table_name = ANY(:tables)"
                ),
                {"tables": list(_TABLES)},
            )
            assert remaining_tables == 0
        finally:
            await connection.rollback()


async def test_create_zero_then_get_by_product_id_round_trips(
    db_session: AsyncSession,
) -> None:
    repo = InventoryRepository(db_session)
    product_id = uuid.uuid4()

    created = await repo.create_zero(product_id)
    await db_session.flush()

    assert created is True
    fetched = await repo.get_by_product_id(product_id)
    assert fetched is not None
    assert fetched.id == product_id
    assert fetched.quantity == 0


async def test_create_zero_is_idempotent_at_the_repository_level(
    db_session: AsyncSession,
) -> None:
    repo = InventoryRepository(db_session)
    product_id = uuid.uuid4()

    first = await repo.create_zero(product_id)
    await db_session.flush()
    second = await repo.create_zero(product_id)
    await db_session.flush()

    assert first is True
    assert second is False


async def test_adjust_persists_new_quantity(db_session: AsyncSession) -> None:
    repo = InventoryRepository(db_session)
    product_id = uuid.uuid4()
    await repo.create_zero(product_id)
    await db_session.flush()

    result = await repo.adjust(product_id, 7, reason="приход")
    await db_session.flush()

    assert result is not None
    assert result.is_ok
    fetched = await repo.get_by_product_id(product_id)
    assert fetched is not None
    assert fetched.quantity == 7


async def test_adjust_rejects_negative_result_without_persisting(
    db_session: AsyncSession,
) -> None:
    repo = InventoryRepository(db_session)
    product_id = uuid.uuid4()
    await repo.create_zero(product_id)
    await db_session.flush()

    result = await repo.adjust(product_id, -1, reason="ошибка")
    await db_session.flush()

    assert result is not None
    assert result.is_err
    assert result.error.code == "negative_stock_adjustment"
    fetched = await repo.get_by_product_id(product_id)
    assert fetched is not None
    assert fetched.quantity == 0


async def test_adjust_returns_none_for_unknown_product(
    db_session: AsyncSession,
) -> None:
    repo = InventoryRepository(db_session)

    result = await repo.adjust(uuid.uuid4(), 1, reason="?")

    assert result is None
