"""RabbitMQ-testcontainers-фикстуры, переиспользуемые сервисами backend/ (ADR 0018).

Подключаются как pytest-плагин из top-level conftest.py сервиса (см.
`test_support.postgres` — то же ограничение pytest)::

    pytest_plugins = ["test_support.rabbitmq"]
"""

from collections.abc import AsyncIterator, Iterator
from urllib.parse import quote

import aio_pika
import pytest
import pytest_asyncio
from aio_pika.abc import AbstractChannel, AbstractRobustConnection
from testcontainers.community.rabbitmq import RabbitMqContainer

RABBITMQ_IMAGE = "rabbitmq:4.1-management"


@pytest.fixture(scope="session")
def rabbitmq_container() -> Iterator[RabbitMqContainer]:
    with RabbitMqContainer(RABBITMQ_IMAGE) as container:
        yield container


@pytest.fixture(scope="session")
def rabbitmq_amqp_url(rabbitmq_container: RabbitMqContainer) -> str:
    """Vhost кодируется явно: голый `/` в конце URI означает vhost `""`, а не
    дефолтный `/` (частая ловушка AMQP URI)."""
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
