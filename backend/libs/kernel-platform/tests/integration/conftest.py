# ruff: noqa: E501
from collections.abc import AsyncIterator, Iterator
from urllib.parse import quote

import aio_pika
import pytest
import pytest_asyncio
from aio_pika.abc import AbstractChannel, AbstractRobustConnection
from testcontainers.community.rabbitmq import RabbitMqContainer

from kernel_platform.outbox.publisher import EVENTS_EXCHANGE_NAME

# Заглушка вместо libs/test-support (issue #99) — этой библиотеки
# ещё нет в дереве. Повторяет паттерн identity-service's
# tests/integration/conftest.py (issue #103), только RabbitMQ-часть:
# declare_topology не трогает Postgres.

RABBITMQ_IMAGE = "rabbitmq:4.1-management"


@pytest.fixture(scope="session")
def rabbitmq_container() -> Iterator[RabbitMqContainer]:
    with RabbitMqContainer(RABBITMQ_IMAGE) as container:
        yield container


@pytest.fixture(scope="session")
def rabbitmq_amqp_url(rabbitmq_container: RabbitMqContainer) -> str:
    """См. identity-service's conftest.py: vhost кодируется явно, голый `/`
    в конце URI означает vhost `""`, а не дефолтный `/`."""
    params = rabbitmq_container.get_connection_params()
    vhost = quote(params.virtual_host, safe="")
    return (
        f"amqp://{params.credentials.username}:{params.credentials.password}"
        f"@{params.host}:{params.port}/{vhost}"
    )


@pytest_asyncio.fixture(scope="module", loop_scope="session")
async def amqp_connection(
    rabbitmq_amqp_url: str,
) -> AsyncIterator[AbstractRobustConnection]:
    connection = await aio_pika.connect_robust(rabbitmq_amqp_url)
    try:
        yield connection
    finally:
        await connection.close()


@pytest_asyncio.fixture(loop_scope="session")
async def channel(
    amqp_connection: AbstractRobustConnection,
) -> AsyncIterator[AbstractChannel]:
    ch = await amqp_connection.channel()
    try:
        yield ch
    finally:
        if not ch.is_closed:
            await ch.close()


@pytest_asyncio.fixture(autouse=True, loop_scope="session")
async def events_exchange_exists(channel: AbstractChannel) -> None:
    """Симулирует объявление identity-service при своём старте :
    `declare_topology` только passive-проверяет `productsflow.events` через
    `get_exchange`, сам его не создаёт."""
    await channel.declare_exchange(
        EVENTS_EXCHANGE_NAME, aio_pika.ExchangeType.TOPIC, durable=True
    )
