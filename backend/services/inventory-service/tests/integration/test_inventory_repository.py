"""Repository round-trip + Alembic-миграция (issue #367, Seams for TDD #7):
`alembic upgrade head` создаёт таблицу `inventory` с PK на `product_id`,
совпадающую с ORM-метаданными; `InventoryRepository` — CRUD round-trip."""

import uuid
from datetime import UTC, datetime, timedelta
from pathlib import Path
from runpy import run_path
from typing import Any

import pytest
from alembic.autogenerate import compare_metadata
from alembic.migration import MigrationContext
from alembic.operations import Operations
from sqlalchemy import Connection, inspect, text
from sqlalchemy.ext.asyncio import AsyncEngine, AsyncSession

from domain.entities.reservation import (
    Reservation,
    ReservationLine,
    ReservationLineStatus,
)
from domain.reservation_status import ReservationStatus
from infrastructure.db import audit as _audit  # noqa: F401
from infrastructure.db.entity_configurations import models as _models
from infrastructure.db.inventory_repository import InventoryRepository
from infrastructure.db.reservation_repository import ReservationRepository

pytestmark = pytest.mark.asyncio(loop_scope="session")

_VERSIONS_DIR = Path(__file__).parents[2] / "src/infrastructure/db/alembic/versions"
_BASE_REVISION = run_path(
    str(_VERSIONS_DIR / "1106f353bbf1_inventory_domain_outbox.py")
)
_RESERVATION_REVISION = run_path(
    str(_VERSIONS_DIR / "c2efd7fcab13_inventory_reservations.py")
)
_TABLES = ("inventory", "inventory_audit_log", "outbox_messages", "processed_messages")
_RESERVATION_TABLES = ("reservation_lines", "reservations", "inbox_messages")


def _run(revision: dict[str, Any], connection: Connection, action: str) -> None:
    migration_context = MigrationContext.configure(connection)
    with Operations.context(migration_context):
        revision[action]()


def _diff_against_orm_metadata(connection: Connection) -> list[Any]:
    migration_context = MigrationContext.configure(connection)
    return compare_metadata(migration_context, _models.Base.metadata)


def _inventory_primary_key_columns(connection: Connection) -> list[str]:
    return inspect(connection).get_pk_constraint("inventory")["constrained_columns"]


def _reservations_primary_key_columns(connection: Connection) -> list[str]:
    return inspect(connection).get_pk_constraint("reservations")["constrained_columns"]


def _reservation_lines_foreign_keys(connection: Connection) -> list[Any]:
    return inspect(connection).get_foreign_keys("reservation_lines")


async def test_alembic_upgrade_to_head_matches_orm_metadata_and_downgrade_reverts(
    db_engine: AsyncEngine,
) -> None:
    """Полная история миграций (issue #367 base + issue #370 reservations,
    Seams for TDD #7) — прогоняется целиком, а не по одной ревизии: diff
    против `Base.metadata` имеет смысл только относительно ГОЛОВЫ истории.

    Гоняем upgrade/diff/downgrade внутри ОДНОЙ транзакции, откатываемой в
    конце (rollback, не commit) — так этот тест не мутирует персистентное
    состояние БД, которое видят другие интеграционные тесты в той же
    session-scoped `_schema` (issue #367): без rollback здесь DROP TABLE
    внутри upgrade() уничтожил бы таблицы, уже созданные ORM-метаданными
    автосоздание-фикстурой conftest.py для всех остальных тестов сессии."""
    async with db_engine.connect() as connection:
        await connection.begin()
        try:
            # `_schema` (tests/integration/conftest.py) уже создал эти
            # таблицы через `Base.metadata.create_all` — чистим их перед
            # прогоном самих Alembic-ревизий, иначе `create_table` упадёт на
            # "relation already exists".
            for table in (*_RESERVATION_TABLES, *_TABLES):
                await connection.execute(text(f"DROP TABLE IF EXISTS {table} CASCADE"))

            await connection.run_sync(
                lambda conn: _run(_BASE_REVISION, conn, "upgrade")
            )
            await connection.run_sync(
                lambda conn: _run(_RESERVATION_REVISION, conn, "upgrade")
            )

            pk_columns = await connection.run_sync(_inventory_primary_key_columns)
            assert pk_columns == ["product_id"]
            reservations_pk = await connection.run_sync(
                _reservations_primary_key_columns
            )
            assert reservations_pk == ["order_id"]
            reservation_lines_fks = await connection.run_sync(
                _reservation_lines_foreign_keys
            )
            assert any(
                fk["referred_table"] == "reservations"
                and fk["constrained_columns"] == ["reservation_id"]
                for fk in reservation_lines_fks
            )

            diffs = await connection.run_sync(_diff_against_orm_metadata)
            assert diffs == []

            await connection.run_sync(
                lambda conn: _run(_RESERVATION_REVISION, conn, "downgrade")
            )
            await connection.run_sync(
                lambda conn: _run(_BASE_REVISION, conn, "downgrade")
            )

            remaining_tables = await connection.scalar(
                text(
                    "SELECT count(*) FROM information_schema.tables "
                    "WHERE table_schema = 'public' AND table_name = ANY(:tables)"
                ),
                {"tables": [*_TABLES, *_RESERVATION_TABLES]},
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


async def test_try_create_then_get_by_order_id_round_trips(
    db_session: AsyncSession,
) -> None:
    repo = ReservationRepository(db_session)
    order_id = uuid.uuid4()
    line = ReservationLine(
        id=uuid.uuid4(),
        product_id=uuid.uuid4(),
        quantity=3,
        status=ReservationLineStatus.CONFIRMED,
    )
    reservation = Reservation.create(
        order_id, lines=[line], ttl_minutes=15, now=datetime.now(UTC)
    )

    created = await repo.try_create(reservation)
    await db_session.flush()

    assert created is True
    fetched = await repo.get_by_order_id(order_id)
    assert fetched is not None
    assert fetched.id == order_id
    assert fetched.status is ReservationStatus.ACTIVE
    assert len(fetched.lines) == 1
    assert fetched.lines[0].product_id == line.product_id
    assert fetched.lines[0].quantity == 3
    assert fetched.lines[0].status is ReservationLineStatus.CONFIRMED


async def test_try_create_is_idempotent_at_the_repository_level(
    db_session: AsyncSession,
) -> None:
    repo = ReservationRepository(db_session)
    order_id = uuid.uuid4()
    reservation = Reservation.create(
        order_id, lines=[], ttl_minutes=15, now=datetime.now(UTC)
    )

    first = await repo.try_create(reservation)
    await db_session.flush()
    second = await repo.try_create(reservation)
    await db_session.flush()

    assert first is True
    assert second is False


async def test_get_by_order_id_returns_none_for_unknown_order(
    db_session: AsyncSession,
) -> None:
    repo = ReservationRepository(db_session)

    fetched = await repo.get_by_order_id(uuid.uuid4())

    assert fetched is None


async def test_save_persists_the_status_transition(db_session: AsyncSession) -> None:
    repo = ReservationRepository(db_session)
    order_id = uuid.uuid4()
    reservation = Reservation.create(
        order_id, lines=[], ttl_minutes=15, now=datetime.now(UTC)
    )
    await repo.try_create(reservation)
    await db_session.flush()

    release_result = reservation.release(reason="manual")
    assert release_result.is_ok
    await repo.save(reservation)
    await db_session.flush()

    fetched = await repo.get_by_order_id(order_id)
    assert fetched is not None
    assert fetched.status is ReservationStatus.RELEASED


async def test_claim_expired_returns_only_active_reservations_past_expiry(
    db_session: AsyncSession,
) -> None:
    repo = ReservationRepository(db_session)
    now = datetime.now(UTC)
    expired = Reservation.create(
        uuid.uuid4(), lines=[], ttl_minutes=15, now=now - timedelta(minutes=30)
    )
    not_yet_expired = Reservation.create(
        uuid.uuid4(), lines=[], ttl_minutes=15, now=now
    )
    await repo.try_create(expired)
    await repo.try_create(not_yet_expired)
    await db_session.flush()

    claimed = await repo.claim_expired(now=now, limit=10)

    assert [reservation.id for reservation in claimed] == [expired.id]
