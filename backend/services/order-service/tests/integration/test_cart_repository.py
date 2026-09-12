"""Repository round-trip + Alembic-миграция (issue #369, Seams for TDD #5):
`alembic upgrade head` создаёт `carts`/`cart_lines` с `UNIQUE(user_id)`/
`UNIQUE(cart_id, product_id)`/`CHECK(quantity > 0)`, совпадающую с
ORM-метаданными; репозиторий — CRUD round-trip; конкурентная первая вставка
одним и тем же `user_id` разрешается через `ON CONFLICT DO NOTHING` и создаёт
ровно одну строку `carts` (D3 TOCTOU-тест)."""

import asyncio
import uuid
from datetime import UTC, datetime
from pathlib import Path
from runpy import run_path
from typing import Any

import pytest
from alembic.autogenerate import compare_metadata
from alembic.migration import MigrationContext
from alembic.operations import Operations
from sqlalchemy import Connection, inspect, select, text
from sqlalchemy.ext.asyncio import AsyncEngine, AsyncSession, async_sessionmaker

from domain.entities.cart import Cart
from infrastructure.db.cart_repository import CartRepository
from infrastructure.db.entity_configurations import models as _models
from infrastructure.db.entity_configurations.models import CartModel

pytestmark = pytest.mark.asyncio(loop_scope="session")

_VERSIONS_DIR = Path(__file__).parents[2] / "src/infrastructure/db/alembic/versions"
_REVISION_FILE = "58907723bd17_carts_and_cart_lines.py"
_REVISION = run_path(str(_VERSIONS_DIR / _REVISION_FILE))
_TABLES = ("cart_lines", "carts")


def _run_revision(connection: Connection, action: str) -> None:
    migration_context = MigrationContext.configure(connection)
    with Operations.context(migration_context):
        _REVISION[action]()


def _diff_against_orm_metadata(connection: Connection) -> list[Any]:
    migration_context = MigrationContext.configure(connection)
    return compare_metadata(migration_context, _models.Base.metadata)


def _carts_pk_columns(connection: Connection) -> list[str]:
    return inspect(connection).get_pk_constraint("carts")["constrained_columns"]


async def test_alembic_upgrade_creates_carts_and_cart_lines_and_downgrade_reverts(
    db_engine: AsyncEngine,
) -> None:
    # upgrade/diff/downgrade внутри ОДНОЙ транзакции, откатываемой в конце —
    # так этот тест не мутирует персистентное состояние, которое видят другие
    # интеграционные тесты в той же session-scoped `_schema` (issue #369).
    async with db_engine.connect() as connection:
        await connection.begin()
        try:
            for table in _TABLES:
                await connection.execute(text(f"DROP TABLE IF EXISTS {table} CASCADE"))

            await connection.run_sync(lambda conn: _run_revision(conn, "upgrade"))

            pk_columns = await connection.run_sync(_carts_pk_columns)
            assert pk_columns == ["id"]

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


async def test_get_or_create_creates_a_cart_for_a_new_user(
    db_session: AsyncSession,
) -> None:
    repo = CartRepository(db_session)
    user_id = uuid.uuid4()

    cart = await repo.get_or_create_for_user(user_id)
    await db_session.flush()

    assert cart.user_id == user_id
    assert cart.lines == []


async def test_get_or_create_is_idempotent_for_the_same_user(
    db_session: AsyncSession,
) -> None:
    repo = CartRepository(db_session)
    user_id = uuid.uuid4()

    first = await repo.get_or_create_for_user(user_id)
    await db_session.flush()
    second = await repo.get_or_create_for_user(user_id)
    await db_session.flush()

    assert first.id.value == second.id.value
    row_count = await db_session.scalar(
        select(CartModel).where(CartModel.user_id == user_id).exists().select()
    )
    assert row_count is True


async def test_get_for_user_returns_none_when_no_cart_exists(
    db_session: AsyncSession,
) -> None:
    repo = CartRepository(db_session)

    cart = await repo.get_for_user(uuid.uuid4())

    assert cart is None


async def test_save_persists_added_line_and_round_trips(
    db_session: AsyncSession,
) -> None:
    repo = CartRepository(db_session)
    user_id = uuid.uuid4()
    cart = await repo.get_or_create_for_user(user_id)
    product_id = uuid.uuid4()
    result = cart.add_line(
        line_id=uuid.uuid4(), product_id=product_id, quantity=3, now=datetime.now(UTC)
    )
    assert result.is_ok

    await repo.save(cart)
    await db_session.flush()

    fetched = await repo.get_for_user(user_id)
    assert fetched is not None
    assert len(fetched.lines) == 1
    assert fetched.lines[0].product_id == product_id
    assert fetched.lines[0].quantity == 3


async def test_save_removes_a_deleted_line(db_session: AsyncSession) -> None:
    repo = CartRepository(db_session)
    user_id = uuid.uuid4()
    cart = await repo.get_or_create_for_user(user_id)
    add_result = cart.add_line(
        line_id=uuid.uuid4(), product_id=uuid.uuid4(), quantity=1, now=datetime.now(UTC)
    )
    line_id = add_result.value.id
    await repo.save(cart)
    await db_session.flush()

    cart.remove_line(line_id=line_id)
    await repo.save(cart)
    await db_session.flush()

    fetched = await repo.get_for_user(user_id)
    assert fetched is not None
    assert fetched.lines == []


async def test_get_line_owner_returns_none_for_unknown_line_id(
    db_session: AsyncSession,
) -> None:
    repo = CartRepository(db_session)

    owner = await repo.get_line_owner(uuid.uuid4())

    assert owner is None


async def test_get_line_owner_returns_the_owning_cart(
    db_session: AsyncSession,
) -> None:
    repo = CartRepository(db_session)
    user_id = uuid.uuid4()
    cart = await repo.get_or_create_for_user(user_id)
    add_result = cart.add_line(
        line_id=uuid.uuid4(), product_id=uuid.uuid4(), quantity=1, now=datetime.now(UTC)
    )
    line_id = add_result.value.id
    await repo.save(cart)
    await db_session.flush()

    owner = await repo.get_line_owner(line_id)

    assert owner is not None
    assert owner.user_id == user_id
    assert len(owner.lines) == 1


async def test_get_or_create_concurrent_calls_create_exactly_one_cart_row(
    db_engine: AsyncEngine,
) -> None:
    """D3 TOCTOU: две параллельные первые `AddCartLine` для одного и того же
    `user_id` не должны создать две строки `carts` — `ON CONFLICT(user_id) DO
    NOTHING` + повторное чтение закрывает гонку. Использует отдельные
    реальные соединения/транзакции (не savepoint-`db_session`), чтобы гонка
    была настоящей; создаёт свою строку с одноразовым `user_id` и подчищает
    её за собой, не полагаясь на session-scoped rollback схемы."""
    user_id = uuid.uuid4()
    sessionmaker = async_sessionmaker(db_engine, expire_on_commit=False)

    async def _get_or_create() -> Cart:
        # Own session -> own real connection/transaction from the pool (not
        # the shared savepoint-`db_session`) so the race is a genuine
        # concurrent commit, not two savepoints on one connection.
        async with sessionmaker() as session:
            repo = CartRepository(session)
            cart = await repo.get_or_create_for_user(user_id)
            await session.commit()
            return cart

    try:
        first, second = await asyncio.gather(_get_or_create(), _get_or_create())

        assert first.id.value == second.id.value

        async with db_engine.connect() as connection:
            count = await connection.scalar(
                text("SELECT count(*) FROM carts WHERE user_id = :user_id"),
                {"user_id": user_id},
            )
            assert count == 1
    finally:
        async with db_engine.begin() as connection:
            await connection.execute(
                text("DELETE FROM carts WHERE user_id = :user_id"), {"user_id": user_id}
            )
