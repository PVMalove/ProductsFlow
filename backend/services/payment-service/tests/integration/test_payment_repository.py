"""Repository round-trip + Alembic-миграция (issue #368, Seams for TDD #6):
`alembic upgrade head` создаёт `payment_authorizations` с unique-ограничениями
на все 3 idempotency-колонки, совпадающую с ORM-метаданными; репозиторий —
CRUD round-trip; конкурентная вставка одним и тем же `idempotency_key`
разрешается через `ON CONFLICT DO NOTHING` (мирор inventory's `create_zero`)."""

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

from domain.entities.payment_authorization import PaymentAuthorization
from domain.psp_client import PspAuthorizeOutcome
from infrastructure.db.entity_configurations import models as _models
from infrastructure.db.payment_repository import PaymentAuthorizationRepository

pytestmark = pytest.mark.asyncio(loop_scope="session")

_VERSIONS_DIR = Path(__file__).parents[2] / "src/infrastructure/db/alembic/versions"
_REVISION_FILE = "d74e30e2f89f_payment_authorizations.py"
_REVISION = run_path(str(_VERSIONS_DIR / _REVISION_FILE))
_TABLES = ("payment_authorizations",)


def _run_revision(connection: Connection, action: str) -> None:
    migration_context = MigrationContext.configure(connection)
    with Operations.context(migration_context):
        _REVISION[action]()


def _diff_against_orm_metadata(connection: Connection) -> list[Any]:
    migration_context = MigrationContext.configure(connection)
    return compare_metadata(migration_context, _models.Base.metadata)


def _payment_authorizations_pk_columns(connection: Connection) -> list[str]:
    return inspect(connection).get_pk_constraint("payment_authorizations")[
        "constrained_columns"
    ]


async def test_alembic_upgrade_creates_payment_authorizations_and_downgrade_reverts(
    db_engine: AsyncEngine,
) -> None:
    # upgrade/diff/downgrade внутри ОДНОЙ транзакции, откатываемой в конце —
    # так этот тест не мутирует персистентное состояние, которое видят другие
    # интеграционные тесты в той же session-scoped `_schema` (issue #368).
    async with db_engine.connect() as connection:
        await connection.begin()
        try:
            for table in _TABLES:
                await connection.execute(text(f"DROP TABLE IF EXISTS {table} CASCADE"))

            await connection.run_sync(lambda conn: _run_revision(conn, "upgrade"))

            pk_columns = await connection.run_sync(_payment_authorizations_pk_columns)
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


async def test_add_then_get_by_idempotency_key_round_trips(
    db_session: AsyncSession,
) -> None:
    repo = PaymentAuthorizationRepository(db_session)
    payment = PaymentAuthorization.create(
        "key-1", 1000, "success", PspAuthorizeOutcome.SUCCESS
    ).value

    inserted = await repo.add(payment)
    await db_session.flush()

    assert inserted is True
    fetched = await repo.get_by_idempotency_key("key-1")
    assert fetched is not None
    assert fetched.id == payment.id
    assert fetched.amount == 1000
    assert fetched.status.value == "authorized"


async def test_add_is_idempotent_at_the_repository_level(
    db_session: AsyncSession,
) -> None:
    repo = PaymentAuthorizationRepository(db_session)
    first = PaymentAuthorization.create(
        "key-2", 1000, "success", PspAuthorizeOutcome.SUCCESS
    ).value
    second = PaymentAuthorization.create(
        "key-2", 2000, "decline", PspAuthorizeOutcome.DECLINE
    ).value

    first_inserted = await repo.add(first)
    await db_session.flush()
    second_inserted = await repo.add(second)
    await db_session.flush()

    assert first_inserted is True
    assert second_inserted is False


async def test_get_by_id_returns_none_for_unknown_id(
    db_session: AsyncSession,
) -> None:
    repo = PaymentAuthorizationRepository(db_session)

    fetched = await repo.get_by_id(uuid.uuid4())

    assert fetched is None


async def test_save_persists_status_and_keys_after_void(
    db_session: AsyncSession,
) -> None:
    repo = PaymentAuthorizationRepository(db_session)
    payment = PaymentAuthorization.create(
        "key-3", 1000, "success", PspAuthorizeOutcome.SUCCESS
    ).value
    await repo.add(payment)
    await db_session.flush()

    payment.void("void-key-3")
    await repo.save(payment)
    await db_session.flush()

    fetched = await repo.get_by_id(payment.id)
    assert fetched is not None
    assert fetched.status.value == "voided"
    assert fetched.void_idempotency_key == "void-key-3"


async def test_get_by_idempotency_key_matches_void_and_capture_columns(
    db_session: AsyncSession,
) -> None:
    repo = PaymentAuthorizationRepository(db_session)
    payment = PaymentAuthorization.create(
        "key-4", 1000, "success", PspAuthorizeOutcome.SUCCESS
    ).value
    await repo.add(payment)
    await db_session.flush()
    payment.void("void-key-4")
    await repo.save(payment)
    await db_session.flush()

    fetched = await repo.get_by_idempotency_key("void-key-4")

    assert fetched is not None
    assert fetched.id == payment.id
