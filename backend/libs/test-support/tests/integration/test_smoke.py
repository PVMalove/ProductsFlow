# ruff: noqa: E501
from collections.abc import AsyncIterator

import pytest
import pytest_asyncio
from aio_pika import DeliveryMode, Message
from aio_pika.abc import AbstractChannel
from sqlalchemy import text
from sqlalchemy.engine import Connection
from sqlalchemy.ext.asyncio import AsyncEngine, AsyncSession

# db_engine/channel привязаны к session-scoped testcontainers, поэтому тесты,
# использующие их, должны идти на одном event loop — тот же приём, что и в
# identity-service/tests/integration/test_smoke.py.
asyncio_session_loop = pytest.mark.asyncio(loop_scope="session")

SMOKE_TABLE = "test_support_smoke_probe"
SMOKE_QUEUE = "test-support.smoke.queue"


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
    # Воспроизводит танец begin+SAVEPOINT+rollback фикстуры db_session
    # напрямую против db_engine (а не через саму фикстуру db_session), чтобы
    # этот тест мог вызвать rollback посреди теста и проверить его эффект на
    # втором, независимом соединении — доказывая, что механизм изоляции
    # действительно отбрасывает записи, а не просто то, что другая
    # транзакция не видит незакоммиченное.
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


# Специально зависит от порядка: доказывает, что собственный teardown
# фикстуры db_session (session.close() + connection.rollback()) реально
# изолирует состояние между тестами — а не только то, что это делает
# воспроизведение выше. Полагается на дефолтный порядок выполнения pytest
# сверху вниз внутри модуля (плагины xdist/randomly к этому сьюту не
# применяются) — тот же приём, что и у rabbitmq purge-тестов в
# identity-service/tests/integration/test_smoke.py.
@asyncio_session_loop
async def test_db_session_fixture_leaves_a_row_for_this_test_only(
    _smoke_probe_table: None, db_session: AsyncSession
) -> None:
    await db_session.execute(text(f"INSERT INTO {SMOKE_TABLE} DEFAULT VALUES"))
    await db_session.flush()

    count = await db_session.scalar(text(f"SELECT count(*) FROM {SMOKE_TABLE}"))
    assert count == 1


@asyncio_session_loop
async def test_db_session_fixture_rolled_back_the_previous_tests_row(
    _smoke_probe_table: None, db_session: AsyncSession
) -> None:
    count = await db_session.scalar(text(f"SELECT count(*) FROM {SMOKE_TABLE}"))
    assert count == 0


@asyncio_session_loop
async def test_rabbitmq_channel_roundtrips_a_message(channel: AbstractChannel) -> None:
    queue = await channel.declare_queue(SMOKE_QUEUE, auto_delete=True)
    await channel.default_exchange.publish(
        Message(b"ping", delivery_mode=DeliveryMode.PERSISTENT),
        routing_key=SMOKE_QUEUE,
    )

    incoming = await queue.get(timeout=5)
    await incoming.ack()

    assert incoming.body == b"ping"
