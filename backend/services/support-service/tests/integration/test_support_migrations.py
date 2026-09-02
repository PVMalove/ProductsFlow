from pathlib import Path
from runpy import run_path
from typing import Any

import pytest
from alembic.autogenerate import compare_metadata
from alembic.migration import MigrationContext
from alembic.operations import Operations
from sqlalchemy import Connection, text
from sqlalchemy.ext.asyncio import AsyncEngine

from infrastructure.db import models as _models  # noqa: F401 — registers ORM tables

asyncio_session_loop = pytest.mark.asyncio(loop_scope="session")

_VERSIONS_DIR = Path(__file__).parents[2] / "src/infrastructure/db/alembic/versions"
_REVISION_FILES = [
    "0001_support_ticket_creation.py",
    "0002_ticket_status_constraint.py",
    "0003_message_moderation.py",
    "0004_user_deletion_inbox.py",
]
_REVISIONS = [run_path(str(_VERSIONS_DIR / name)) for name in _REVISION_FILES]

_TABLES = ("processed_messages", "ticket_messages", "tickets", "outbox_messages")


def _run_revision(
    connection: Connection, revision: dict[str, Any], action: str
) -> None:
    migration_context = MigrationContext.configure(connection)
    with Operations.context(migration_context):
        revision[action]()


def _upgrade_all(connection: Connection) -> None:
    for revision in _REVISIONS:
        _run_revision(connection, revision, "upgrade")


def _downgrade_all(connection: Connection) -> None:
    for revision in reversed(_REVISIONS):
        _run_revision(connection, revision, "downgrade")


def _diff_against_orm_metadata(connection: Connection) -> list[Any]:
    migration_context = MigrationContext.configure(connection)
    return compare_metadata(migration_context, _models.Base.metadata)


async def _drop_support_schema(db_engine: AsyncEngine) -> None:
    async with db_engine.begin() as connection:
        for table in _TABLES:
            await connection.execute(text(f"DROP TABLE IF EXISTS {table} CASCADE"))


@asyncio_session_loop
async def test_alembic_upgrade_reproduces_orm_schema_and_downgrade_reverts_cleanly(
    db_engine: AsyncEngine,
) -> None:
    await _drop_support_schema(db_engine)
    try:
        async with db_engine.begin() as connection:
            await connection.run_sync(_upgrade_all)

            diffs = await connection.run_sync(_diff_against_orm_metadata)
            assert diffs == []

            await connection.run_sync(_downgrade_all)

            remaining_tables = await connection.scalar(
                text(
                    "SELECT count(*) FROM information_schema.tables "
                    "WHERE table_schema = 'public' AND table_name = ANY(:tables)"
                ),
                {"tables": list(_TABLES)},
            )
        assert remaining_tables == 0
    finally:
        await _drop_support_schema(db_engine)
