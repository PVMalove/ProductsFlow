from pathlib import Path
from runpy import run_path
from typing import Any

import pytest
from alembic.migration import MigrationContext
from alembic.operations import Operations
from sqlalchemy import Connection, text
from sqlalchemy.ext.asyncio import AsyncEngine

asyncio_session_loop = pytest.mark.asyncio(loop_scope="session")

_VERSIONS_DIR = Path(__file__).parents[2] / "src/infrastructure/db/alembic/versions"
_CREATE_REVISION = run_path(
    str(_VERSIONS_DIR / "672e9d689f15_create_outbox_messages.py")
)
_TRIGGER_REVISION = run_path(
    str(_VERSIONS_DIR / "05fc06c154bc_outbox_messages_notify_trigger.py")
)
_UUID_REVISION = run_path(
    str(_VERSIONS_DIR / "c1a7e6e6a4f2_outbox_aggregate_id_uuid.py")
)


def _run_revision(
    connection: Connection, revision: dict[str, Any], action: str
) -> None:
    migration_context = MigrationContext.configure(connection)
    with Operations.context(migration_context):
        revision[action]()


def _upgrade_to_trigger(connection: Connection) -> None:
    _run_revision(connection, _CREATE_REVISION, "upgrade")
    _run_revision(connection, _TRIGGER_REVISION, "upgrade")


def _upgrade_to_uuid(connection: Connection) -> None:
    _upgrade_to_trigger(connection)
    _run_revision(connection, _UUID_REVISION, "upgrade")


def _downgrade_uuid(connection: Connection) -> None:
    _run_revision(connection, _UUID_REVISION, "downgrade")


async def _drop_outbox_schema(db_engine: AsyncEngine) -> None:
    async with db_engine.begin() as connection:
        await connection.execute(
            text("DROP FUNCTION IF EXISTS notify_outbox_insert() CASCADE")
        )
        await connection.execute(text("DROP TABLE IF EXISTS outbox_messages CASCADE"))


@asyncio_session_loop
async def test_alembic_chain_changes_outbox_aggregate_id_to_uuid_and_back(
    db_engine: AsyncEngine,
) -> None:
    await _drop_outbox_schema(db_engine)
    try:
        async with db_engine.begin() as connection:
            await connection.run_sync(_upgrade_to_uuid)
            upgraded_type = await connection.scalar(
                text(
                    "SELECT udt_name FROM information_schema.columns "
                    "WHERE table_name = 'outbox_messages' "
                    "AND column_name = 'aggregate_id'"
                )
            )

            await connection.run_sync(_downgrade_uuid)
            downgraded_type = await connection.scalar(
                text(
                    "SELECT udt_name FROM information_schema.columns "
                    "WHERE table_name = 'outbox_messages' "
                    "AND column_name = 'aggregate_id'"
                )
            )

        assert upgraded_type == "uuid"
        assert downgraded_type == "int8"
    finally:
        await _drop_outbox_schema(db_engine)


@asyncio_session_loop
async def test_upgrade_refuses_nonempty_legacy_outbox(
    db_engine: AsyncEngine,
) -> None:
    await _drop_outbox_schema(db_engine)
    try:
        async with db_engine.begin() as connection:
            await connection.run_sync(_upgrade_to_trigger)
            await connection.execute(
                text(
                    "INSERT INTO outbox_messages "
                    "(aggregate_type, aggregate_id, event_type, payload, occurred_at) "
                    "VALUES ('User', 7, 'user.registered.v1', '{}', now())"
                )
            )

            with pytest.raises(Exception, match="outbox_messages must be empty"):
                await connection.run_sync(
                    lambda sync_connection: _run_revision(
                        sync_connection, _UUID_REVISION, "upgrade"
                    )
                )
    finally:
        await _drop_outbox_schema(db_engine)


@asyncio_session_loop
async def test_downgrade_refuses_nonempty_uuid_outbox(
    db_engine: AsyncEngine,
) -> None:
    await _drop_outbox_schema(db_engine)
    try:
        async with db_engine.begin() as connection:
            await connection.run_sync(_upgrade_to_uuid)
            await connection.execute(
                text(
                    "INSERT INTO outbox_messages "
                    "(aggregate_type, aggregate_id, event_type, payload, occurred_at) "
                    "VALUES ('User', '00000000-0000-0000-0000-000000000007', "
                    "'user.registered.v1', '{}', now())"
                )
            )

            with pytest.raises(Exception, match="outbox_messages must be empty"):
                await connection.run_sync(
                    lambda sync_connection: _run_revision(
                        sync_connection, _UUID_REVISION, "downgrade"
                    )
                )
    finally:
        await _drop_outbox_schema(db_engine)
