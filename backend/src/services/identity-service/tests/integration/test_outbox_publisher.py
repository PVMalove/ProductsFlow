import json
from collections.abc import AsyncIterator
from datetime import UTC, datetime

import aio_pika
import pytest
import pytest_asyncio
from aio_pika import DeliveryMode
from aio_pika.abc import AbstractExchange, AbstractRobustConnection
from kernel_platform.outbox.models import Base, OutboxMessage
from kernel_platform.outbox.publisher import OutboxPublisher
from sqlalchemy import select, text
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
async def amqp_connection(
    rabbitmq_amqp_url: str,
) -> AsyncIterator[AbstractRobustConnection]:
    connection = await aio_pika.connect_robust(rabbitmq_amqp_url)
    try:
        yield connection
    finally:
        await connection.close()


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
