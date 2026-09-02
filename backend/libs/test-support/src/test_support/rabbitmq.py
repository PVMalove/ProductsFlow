# ruff: noqa: E501
"""RabbitMQ-testcontainers-фикстуры, переиспользуемые сервисами backend/ .

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
    """Поднимает RabbitMQ через testcontainers.

    Контейнер крутится весь тест-ран (`session` scope). Очищается автоматически демоном Ryuk.

    Yields:
        RabbitMqContainer: Поднятый контейнер."""
    with RabbitMqContainer(RABBITMQ_IMAGE) as container:
        yield container


@pytest.fixture(scope="session")
def rabbitmq_amqp_url(rabbitmq_container: RabbitMqContainer) -> str:
    """Склеивает креды и хосты из контейнера в валидный AMQP URI.

    Особое внимание уделяется URL-кодированию дефолтного vhost (`/`), который превращается в пустую строку при квотинге (если `safe=""`), чтобы не было путаницы в aio-pika.

    Args:
        rabbitmq_container (RabbitMqContainer): Запущенный RabbitMQ.

    Returns:
        str: Строка подключения формата `amqp://user:pass@host:port/vhost`."""
    params = rabbitmq_container.get_connection_params()
    vhost = quote(params.virtual_host, safe="")
    return f"amqp://{params.credentials.username}:{params.credentials.password}@{params.host}:{params.port}/{vhost}"


@pytest_asyncio.fixture(scope="module", loop_scope="session")
async def amqp_connection(
    rabbitmq_amqp_url: str,
) -> AsyncIterator[AbstractRobustConnection]:
    """Открывает robust коннекшен к кролику с автореконнектом.

    Открывается один раз на модуль. По завершении аккуратно закрывает сокет.

    Args:
        rabbitmq_amqp_url (str): URI кролика.

    Yields:
        AbstractRobustConnection: Установленное AMQP-соединение."""
    connection = await aio_pika.connect_robust(rabbitmq_amqp_url)
    try:
        yield connection
    finally:
        await connection.close()


@pytest_asyncio.fixture(loop_scope="session")
async def channel(
    amqp_connection: AbstractRobustConnection,
) -> AsyncIterator[AbstractChannel]:
    """Мультиплексирует канал внутри `amqp_connection` для теста.

    Отдельный канал изолирует стейт (например, префетчи, неподтвержденные месседжи) между тестами. По завершении гарантированно закрывается, если не был закрыт вручную.

    Args:
        amqp_connection (AbstractRobustConnection): Соединение.

    Yields:
        AbstractChannel: AMQP-канал."""
    ch = await amqp_connection.channel()
    try:
        yield ch
    finally:
        if not ch.is_closed:
            await ch.close()
