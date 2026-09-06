# ruff: noqa: E501
"""Redis-testcontainers-фикстуры, переиспользуемые сервисами backend/ .

Подключаются как pytest-плагин из top-level conftest.py сервиса (см.
`test_support.postgres` — то же ограничение pytest)::

    pytest_plugins = ["test_support.redis"]
"""

from collections.abc import AsyncIterator, Iterator

import pytest
import pytest_asyncio
from redis.asyncio import Redis
from testcontainers.community.redis import RedisContainer

REDIS_IMAGE = "redis:8.2-alpine"


@pytest.fixture(scope="session")
def redis_container() -> Iterator[RedisContainer]:
    """Поднимает Redis через testcontainers.

    Контейнер крутится весь тест-ран (`session` scope). Очищается автоматически демоном Ryuk.

    Yields:
        RedisContainer: Поднятый контейнер."""
    with RedisContainer(REDIS_IMAGE) as container:
        yield container


@pytest.fixture(scope="session")
def redis_url(redis_container: RedisContainer) -> str:
    """Склеивает хост и порт тестконтейнера в валидный `redis://`-URL.

    Args:
        redis_container (RedisContainer): Запущенный Redis.

    Returns:
        str: Строка подключения формата `redis://host:port/0`."""
    host = redis_container.get_container_host_ip()
    port = redis_container.get_exposed_port(redis_container.port)
    return f"redis://{host}:{port}/0"


@pytest_asyncio.fixture(loop_scope="session")
async def redis_client(redis_url: str) -> AsyncIterator[Redis]:
    """Открывает асинхронный клиент к тестконтейнеру для конкретного теста.

    Флашит базу перед выдачей клиента, так что тесты не аффектят друг друга,
    несмотря на общий (`session`-scope) контейнер.

    Args:
        redis_url (str): URI контейнера.

    Yields:
        Redis[str]: Асинхронный клиент с `decode_responses=True`."""
    client: Redis = Redis.from_url(redis_url, decode_responses=True)
    try:
        await client.flushdb()
        yield client
    finally:
        await client.aclose()
