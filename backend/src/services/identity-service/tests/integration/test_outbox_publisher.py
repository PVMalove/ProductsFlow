import asyncio
import json
from collections.abc import AsyncIterator
from datetime import UTC, datetime, timedelta

import aio_pika
import pytest
import pytest_asyncio
from aio_pika import DeliveryMode
from aio_pika.abc import AbstractExchange, AbstractRobustConnection
from kernel_platform.outbox.models import Base, OutboxMessage
from kernel_platform.outbox.publisher import OutboxPublisher
from sqlalchemy import select, text, update
from sqlalchemy.ext.asyncio import AsyncEngine, async_sessionmaker

# db_engine/rabbitmq_amqp_url bind to the session-scoped testcontainers, so
# tests exercising both must run on that same event loop — same reasoning as
# tests/integration/test_smoke.py.
asyncio_session_loop = pytest.mark.asyncio(loop_scope="session")

TEST_EXCHANGE_NAME = "productsflow.events.outbox-publisher-test"
ROUTED_QUEUE = "identity.outbox-publisher-test.routed"
ROUTED_ROUTING_KEY = "user.registered.v1"
UNROUTED_ROUTING_KEY = "user.orphaned.v1"


@pytest_asyncio.fixture(scope="module", loop_scope="session")
async def _outbox_table(db_engine: AsyncEngine) -> AsyncIterator[None]:
    async with db_engine.begin() as connection:
        await connection.run_sync(Base.metadata.create_all)
    try:
        yield
    finally:
        async with db_engine.begin() as connection:
            await connection.run_sync(Base.metadata.drop_all)


@pytest_asyncio.fixture(loop_scope="session")
async def _clear_outbox_after_test(
    db_engine: AsyncEngine, _outbox_table: None
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
        # Очищаем очередь, а не только объявление — сообщения, оставшиеся
        # неконсьюмленными, иначе переживают тест и ломают изоляцию для
        # следующего запуска этого модуля.
        await queue.purge()


async def _insert_row(
    session_factory: async_sessionmaker, *, event_type: str
) -> OutboxMessage:
    row = OutboxMessage(
        aggregate_type="User",
        aggregate_id=7,
        event_type=event_type,
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


async def _retry_state(
    session_factory: async_sessionmaker, row_id: int
) -> tuple[int, datetime | None]:
    async with session_factory() as session:
        result = await session.execute(
            select(OutboxMessage.attempts, OutboxMessage.next_attempt_at).where(
                OutboxMessage.id == row_id
            )
        )
        return result.one()


@asyncio_session_loop
async def test_run_once_delivers_a_routed_row_and_marks_it_published(
    db_engine: AsyncEngine,
    amqp_connection: AbstractRobustConnection,
    events_exchange: AbstractExchange,
    _clear_outbox_after_test: None,
) -> None:
    session_factory = async_sessionmaker(db_engine, expire_on_commit=False)
    row = await _insert_row(session_factory, event_type=ROUTED_ROUTING_KEY)

    publisher = OutboxPublisher(session_factory, events_exchange)
    await publisher.run_once()

    channel = await amqp_connection.channel()
    queue = await channel.get_queue(ROUTED_QUEUE)
    message = await queue.get(timeout=5)
    await message.ack()

    assert message.message_id == str(row.id)
    assert message.delivery_mode == DeliveryMode.PERSISTENT
    assert message.headers["traceparent"] == "00-test-trace-01"
    assert json.loads(message.body) == {"id": 7, "username": "alice"}
    assert await _published_at(session_factory, row.id) is not None


@asyncio_session_loop
async def test_run_once_leaves_an_unroutable_row_unpublished(
    db_engine: AsyncEngine,
    events_exchange: AbstractExchange,
    _clear_outbox_after_test: None,
) -> None:
    session_factory = async_sessionmaker(db_engine, expire_on_commit=False)
    row = await _insert_row(session_factory, event_type=UNROUTED_ROUTING_KEY)

    publisher = OutboxPublisher(session_factory, events_exchange)
    await publisher.run_once()

    assert await _published_at(session_factory, row.id) is None
    attempts, next_attempt_at = await _retry_state(session_factory, row.id)
    assert attempts == 1
    assert next_attempt_at is not None
    assert next_attempt_at > datetime.now(UTC)


@asyncio_session_loop
async def test_run_once_skips_a_row_whose_next_attempt_at_is_in_the_future(
    db_engine: AsyncEngine,
    events_exchange: AbstractExchange,
    _clear_outbox_after_test: None,
) -> None:
    session_factory = async_sessionmaker(db_engine, expire_on_commit=False)
    row = await _insert_row(session_factory, event_type=ROUTED_ROUTING_KEY)
    async with session_factory() as session:
        await session.execute(
            update(OutboxMessage)
            .where(OutboxMessage.id == row.id)
            .values(next_attempt_at=datetime.now(UTC) + timedelta(hours=1))
        )
        await session.commit()

    publisher = OutboxPublisher(session_factory, events_exchange)
    await publisher.run_once()

    assert await _published_at(session_factory, row.id) is None
    attempts, _ = await _retry_state(session_factory, row.id)
    assert attempts == 0


@asyncio_session_loop
async def test_a_row_claimed_but_never_committed_is_still_delivered_after_restart(
    db_engine: AsyncEngine,
    amqp_connection: AbstractRobustConnection,
    events_exchange: AbstractExchange,
    _clear_outbox_after_test: None,
) -> None:
    """Симулирует kill-restart (ADR 0014, issue #101, тест (а) из DoD Фазы
    2b TD): соединение обрывается после `SELECT ... FOR UPDATE`, но до
    коммита. `async with session_factory()` без `commit()` откатывает
    транзакцию на выходе — так же, как обрыв соединения к Postgres снял бы
    блокировку. Строка должна остаться доставляемой следующим циклом.
    """
    session_factory = async_sessionmaker(db_engine, expire_on_commit=False)
    row = await _insert_row(session_factory, event_type=ROUTED_ROUTING_KEY)

    async with session_factory() as crashed_session:
        claimed = (
            await crashed_session.scalars(
                select(OutboxMessage)
                .where(OutboxMessage.id == row.id)
                .with_for_update(skip_locked=True)
            )
        ).all()
        assert [claimed_row.id for claimed_row in claimed] == [row.id]
        # без commit(): выход из `async with` откатывает транзакцию,
        # снимая блокировку — как при обрыве соединения к Postgres.

    restarted_publisher = OutboxPublisher(session_factory, events_exchange)
    await restarted_publisher.run_once()

    channel = await amqp_connection.channel()
    queue = await channel.get_queue(ROUTED_QUEUE)
    message = await queue.get(timeout=5)
    await message.ack()

    assert message.message_id == str(row.id)
    assert await _published_at(session_factory, row.id) is not None


@asyncio_session_loop
async def test_two_parallel_publishers_never_deliver_the_same_row_twice(
    db_engine: AsyncEngine,
    amqp_connection: AbstractRobustConnection,
    events_exchange: AbstractExchange,
    _clear_outbox_after_test: None,
) -> None:
    session_factory = async_sessionmaker(db_engine, expire_on_commit=False)
    rows = [
        await _insert_row(session_factory, event_type=ROUTED_ROUTING_KEY)
        for _ in range(5)
    ]

    publisher_a = OutboxPublisher(session_factory, events_exchange)
    publisher_b = OutboxPublisher(session_factory, events_exchange)
    await asyncio.gather(publisher_a.run_once(), publisher_b.run_once())

    channel = await amqp_connection.channel()
    queue = await channel.get_queue(ROUTED_QUEUE)
    delivered_ids = set()
    for _ in rows:
        message = await queue.get(timeout=5)
        await message.ack()
        delivered_ids.add(message.message_id)

    assert delivered_ids == {str(row.id) for row in rows}
    for row in rows:
        assert await _published_at(session_factory, row.id) is not None
