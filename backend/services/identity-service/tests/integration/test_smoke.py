from collections.abc import AsyncIterator

import pytest
import pytest_asyncio
from pika.adapters.blocking_connection import BlockingChannel
from sqlalchemy import text
from sqlalchemy.engine import Connection
from sqlalchemy.ext.asyncio import AsyncEngine, AsyncSession

from tests.integration.conftest import SMOKE_QUEUE

# db_engine binds to the session-scoped Postgres container, so the Postgres
# tests below must run on that same event loop (asyncpg connections are
# loop-bound) — same reasoning as the monolith's tests/integration/test_smoke.py.
# Applied per-test, not as a module-level pytestmark, since this module also
# has plain sync tests (pika has no async API).
asyncio_session_loop = pytest.mark.asyncio(loop_scope="session")

SMOKE_TABLE = "identity_smoke_probe"


@pytest_asyncio.fixture(scope="module", loop_scope="session")
async def _smoke_probe_table(db_engine: AsyncEngine) -> AsyncIterator[None]:
    async with db_engine.begin() as connection:
        await connection.execute(
            text(f"CREATE TABLE {SMOKE_TABLE} (id serial PRIMARY KEY)")
        )
    try:
        yield
    finally:
        async with db_engine.begin() as connection:
            await connection.execute(text(f"DROP TABLE {SMOKE_TABLE}"))


@asyncio_session_loop
async def test_postgres_container_is_reachable(db_engine: AsyncEngine) -> None:
    async with db_engine.connect() as connection:
        result = await connection.execute(text("SELECT 1"))

    assert result.scalar() == 1


@asyncio_session_loop
async def test_db_session_rollback_isolates_writes_between_tests(
    _smoke_probe_table: None, db_engine: AsyncEngine
) -> None:
    # Reproduces the db_session fixture's begin+SAVEPOINT+rollback dance
    # directly against db_engine (rather than using the db_session fixture
    # itself), so this test can trigger the rollback mid-test and check its
    # effect on a second, independent connection — proving the isolation
    # mechanism actually discards writes, not just that another transaction
    # can't see uncommitted ones.
    def _count(connection: Connection) -> int | None:
        return connection.execute(text(f"SELECT count(*) FROM {SMOKE_TABLE}")).scalar()

    async with db_engine.connect() as connection:
        await connection.begin()
        session = AsyncSession(
            bind=connection, join_transaction_mode="create_savepoint"
        )
        await session.execute(text(f"INSERT INTO {SMOKE_TABLE} DEFAULT VALUES"))
        await session.flush()

        assert await connection.run_sync(_count) == 1

        await session.close()
        await connection.rollback()

    async with db_engine.connect() as connection:
        assert await connection.run_sync(_count) == 0


def test_rabbitmq_channel_is_reachable(rabbitmq_channel: BlockingChannel) -> None:
    assert rabbitmq_channel.is_open


# Order-dependent by design: proves the rabbitmq_channel fixture's teardown
# purge actually isolates state between tests, not just that a fresh queue
# starts empty. Relies on pytest's default top-to-bottom execution order
# within a module (no xdist/randomly plugin runs against this suite).
def test_rabbitmq_channel_leaves_a_message_for_the_next_test(
    rabbitmq_channel: BlockingChannel,
) -> None:
    rabbitmq_channel.basic_publish(
        exchange="", routing_key=SMOKE_QUEUE, body=b"leftover"
    )


def test_rabbitmq_channel_purge_discarded_the_previous_tests_message(
    rabbitmq_channel: BlockingChannel,
) -> None:
    method_frame, _, _ = rabbitmq_channel.basic_get(queue=SMOKE_QUEUE, auto_ack=True)

    assert method_frame is None
