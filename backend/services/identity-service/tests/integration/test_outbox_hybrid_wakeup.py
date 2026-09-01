import time
import uuid
from collections.abc import AsyncIterator
from datetime import UTC, datetime

import aio_pika
import pytest
import pytest_asyncio
from aio_pika.abc import AbstractExchange, AbstractRobustConnection
from kernel_platform.outbox.listener import (
    NOTIFICATION_CHANNEL,
    OutboxListener,
    to_asyncpg_dsn,
)
from kernel_platform.outbox.models import Base, OutboxMessage
from kernel_platform.outbox.publisher import OutboxPublisher
from sqlalchemy import select, text
from sqlalchemy.ext.asyncio import AsyncEngine, async_sessionmaker
from testcontainers.community.postgres import PostgresContainer

# db_engine/rabbitmq_amqp_url/postgres_container bind to the session-scoped
# testcontainers, so tests exercising them must run on that same event loop —
# same reasoning as tests/integration/test_smoke.py and test_outbox_publisher.py.
asyncio_session_loop = pytest.mark.asyncio(loop_scope="session")

TEST_EXCHANGE_NAME = "productsflow.events.outbox-hybrid-wakeup-test"
ROUTED_QUEUE = "identity.outbox-hybrid-wakeup-test.routed"
ROUTED_ROUTING_KEY = "user.registered.v1"

# Poll-интервал в этих тестах намеренно длинный/короткий относительно
# реального дефолта (identity_outbox_poll_interval_seconds=5.0) — длинный
# делает latency-разницу NOTIFY-vs-poll недвусмысленной, короткий не даёт
# regression-тесту растягиваться без необходимости.
LONG_POLL_INTERVAL_SECONDS = 6.0
SHORT_POLL_INTERVAL_SECONDS = 1.0


@pytest_asyncio.fixture(scope="module", loop_scope="session")
async def _outbox_table_with_notify_trigger(
    db_engine: AsyncEngine,
) -> AsyncIterator[None]:
    """Повторяет DDL Alembic-ревизии 05fc06c154bc (`op.execute` в её
    `upgrade()`) напрямую против testcontainers Postgres — этот дереву тестов
    ещё не прогоняет реальные Alembic-миграции (см. `_outbox_table` в
    test_outbox_publisher.py, тот же паттерн для самой таблицы).
    """
    async with db_engine.begin() as connection:
        await connection.run_sync(Base.metadata.create_all)
        await connection.execute(
            text(
                f"""
                CREATE FUNCTION notify_outbox_insert() RETURNS trigger AS $$
                BEGIN
                    PERFORM pg_notify('{NOTIFICATION_CHANNEL}', NEW.id::text);
                    RETURN NEW;
                END;
                $$ LANGUAGE plpgsql;
                """
            )
        )
        await connection.execute(
            text(
                """
                CREATE TRIGGER outbox_messages_notify_insert
                AFTER INSERT ON outbox_messages
                FOR EACH ROW EXECUTE FUNCTION notify_outbox_insert();
                """
            )
        )
    try:
        yield
    finally:
        async with db_engine.begin() as connection:
            await connection.execute(
                text("DROP TRIGGER outbox_messages_notify_insert ON outbox_messages")
            )
            await connection.execute(text("DROP FUNCTION notify_outbox_insert()"))
            await connection.run_sync(Base.metadata.drop_all)


@pytest_asyncio.fixture(loop_scope="session")
async def _clear_outbox_after_test(
    db_engine: AsyncEngine, _outbox_table_with_notify_trigger: None
) -> AsyncIterator[None]:
    try:
        yield
    finally:
        async with db_engine.begin() as connection:
            await connection.execute(text("DELETE FROM outbox_messages"))


@pytest_asyncio.fixture(scope="module", loop_scope="session")
async def events_exchange(
    amqp_connection: AbstractRobustConnection,
) -> AsyncIterator[AbstractExchange]:
    channel = await amqp_connection.channel()
    exchange = await channel.declare_exchange(
        TEST_EXCHANGE_NAME, aio_pika.ExchangeType.TOPIC, durable=True
    )
    queue = await channel.declare_queue(ROUTED_QUEUE, durable=True)
    await queue.bind(exchange, routing_key=ROUTED_ROUTING_KEY)
    try:
        yield exchange
    finally:
        await queue.purge()


async def _insert_row(session_factory: async_sessionmaker) -> OutboxMessage:
    row = OutboxMessage(
        aggregate_type="User",
        aggregate_id=uuid.uuid4(),
        event_type=ROUTED_ROUTING_KEY,
        payload={"id": 7, "username": "alice"},
        occurred_at=datetime.now(UTC),
        trace_context="00-test-trace-01",
    )
    async with session_factory() as session:
        session.add(row)
        await session.commit()
    return row


async def _published_at(
    session_factory: async_sessionmaker, row_id: int
) -> datetime | None:
    async with session_factory() as session:
        return await session.scalar(
            select(OutboxMessage.published_at).where(OutboxMessage.id == row_id)
        )


@asyncio_session_loop
async def test_notify_delivers_a_new_row_faster_than_the_poll_interval(
    db_engine: AsyncEngine,
    postgres_container: PostgresContainer,
    amqp_connection: AbstractRobustConnection,
    events_exchange: AbstractExchange,
    _clear_outbox_after_test: None,
) -> None:
    session_factory = async_sessionmaker(db_engine, expire_on_commit=False)
    publisher = OutboxPublisher(session_factory, events_exchange)
    dsn = to_asyncpg_dsn(postgres_container.get_connection_url())

    async with OutboxListener(dsn) as listener:
        await publisher.run_once()  # эмулирует стартовый цикл воркера — очередь пуста

        started_at = time.monotonic()
        row = await _insert_row(session_factory)
        await listener.wait_for_wakeup(timeout=LONG_POLL_INTERVAL_SECONDS)
        await publisher.run_once()
        elapsed = time.monotonic() - started_at

    # NOTIFY разбудил ожидание задолго до истечения LONG_POLL_INTERVAL_SECONDS
    # — иначе elapsed был бы близок к самому таймауту.
    assert elapsed < LONG_POLL_INTERVAL_SECONDS / 2

    channel = await amqp_connection.channel()
    queue = await channel.get_queue(ROUTED_QUEUE)
    message = await queue.get(timeout=5)
    await message.ack()
    assert message.message_id == str(row.id)
    assert await _published_at(session_factory, row.id) is not None


@asyncio_session_loop
async def test_a_row_inserted_before_subscribing_is_still_delivered_by_the_next_poll(
    db_engine: AsyncEngine,
    postgres_container: PostgresContainer,
    amqp_connection: AbstractRobustConnection,
    events_exchange: AbstractExchange,
    _clear_outbox_after_test: None,
) -> None:
    """Регресс-тест потерянного `NOTIFY` (ADR 0014, issue #102): триггер
    стреляет `pg_notify` в момент вставки, но воркер ещё не подписан на
    канал — Postgres не ставит уведомление в очередь для будущего
    подписчика, оно теряется безвозвратно, ровно как при рестарте воркера.
    Доставка всё равно должна произойти на следующем poll-тике.
    """
    session_factory = async_sessionmaker(db_engine, expire_on_commit=False)
    publisher = OutboxPublisher(session_factory, events_exchange)

    row = await _insert_row(session_factory)

    dsn = to_asyncpg_dsn(postgres_container.get_connection_url())
    async with OutboxListener(dsn) as listener:
        started_at = time.monotonic()
        await listener.wait_for_wakeup(timeout=SHORT_POLL_INTERVAL_SECONDS)
        elapsed = time.monotonic() - started_at
        await publisher.run_once()

    # Ожидание дошло до таймаута — NOTIFY, отправленный до подписки, сюда
    # не долетел, доставка обязана произойти через poll-fallback ниже.
    assert elapsed >= SHORT_POLL_INTERVAL_SECONDS
    assert await _published_at(session_factory, row.id) is not None

    channel = await amqp_connection.channel()
    queue = await channel.get_queue(ROUTED_QUEUE)
    message = await queue.get(timeout=5)
    await message.ack()
    assert message.message_id == str(row.id)
