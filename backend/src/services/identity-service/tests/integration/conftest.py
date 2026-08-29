from collections.abc import AsyncIterator, Iterator

import pika
import pytest
import pytest_asyncio
from pika.adapters.blocking_connection import BlockingChannel
from sqlalchemy.ext.asyncio import AsyncEngine, AsyncSession, create_async_engine
from testcontainers.community.postgres import PostgresContainer
from testcontainers.community.rabbitmq import RabbitMqContainer

# Заглушка вместо libs/test-support (ADR 0018, issue #99) — этой библиотеки
# ещё нет в дереве. Postgres-часть повторяет паттерн tests/conftest.py
# монолита; RabbitMQ-часть — первая в этом репозитории.

POSTGRES_IMAGE = "postgres:18.0"
RABBITMQ_IMAGE = "rabbitmq:4.1-management"

SMOKE_QUEUE = "identity.smoke.queue"


@pytest.fixture(scope="session")
def postgres_container() -> Iterator[PostgresContainer]:
    with PostgresContainer(POSTGRES_IMAGE, driver="asyncpg") as container:
        yield container


@pytest_asyncio.fixture(scope="session", loop_scope="session")
async def db_engine(
    postgres_container: PostgresContainer,
) -> AsyncIterator[AsyncEngine]:
    engine = create_async_engine(postgres_container.get_connection_url())
    try:
        yield engine
    finally:
        await engine.dispose()


@pytest_asyncio.fixture(loop_scope="session")
async def db_session(db_engine: AsyncEngine) -> AsyncIterator[AsyncSession]:
    async with db_engine.connect() as connection:
        await connection.begin()
        session = AsyncSession(
            bind=connection, join_transaction_mode="create_savepoint"
        )
        try:
            yield session
        finally:
            await session.close()
            await connection.rollback()


@pytest.fixture(scope="session")
def rabbitmq_container() -> Iterator[RabbitMqContainer]:
    with RabbitMqContainer(RABBITMQ_IMAGE) as container:
        yield container


@pytest.fixture
def rabbitmq_channel(
    rabbitmq_container: RabbitMqContainer,
) -> Iterator[BlockingChannel]:
    connection = pika.BlockingConnection(rabbitmq_container.get_connection_params())
    channel = connection.channel()
    channel.queue_declare(queue=SMOKE_QUEUE)
    channel.queue_purge(queue=SMOKE_QUEUE)
    try:
        yield channel
    finally:
        # Очищаем очередь, а не только закрываем канал — сообщения, оставшиеся
        # неподтверждёнными или неконсьюмленными, иначе переживают тест и
        # ломают изоляцию для следующего.
        channel.queue_purge(queue=SMOKE_QUEUE)
        connection.close()
