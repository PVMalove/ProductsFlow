from collections.abc import AsyncIterator

import aio_pika
import pytest
import pytest_asyncio
from aio_pika import ExchangeType
from aio_pika.abc import AbstractChannel, AbstractRobustConnection
from kernel_platform.outbox.publisher import EVENTS_EXCHANGE_NAME
from kernel_platform.topology import DLX_EXCHANGE_NAME, declare_topology

# amqp_connection (conftest.py) — module-scoped, bound к session-scoped
# event loop; тесты и фикстуры этого модуля должны идти на том же loop —
# см. identity-service's tests/integration/test_outbox_publisher.py.
pytestmark = pytest.mark.asyncio(loop_scope="session")

SERVICE_NAME = "kernel-topology-test"
MAIN_QUEUE_NAME = f"{SERVICE_NAME}.user-events"
DLQ_NAME = f"{MAIN_QUEUE_NAME}.dlq"
RETRY_STAGE_TTL_MS = {
    "retry.5s": 5_000,
    "retry.30s": 30_000,
    "retry.2m": 120_000,
}


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
    """Симулирует объявление identity-service при своём старте (ADR 0015):
    `declare_topology` только passive-проверяет `productsflow.events` через
    `get_exchange`, сам его не создаёт."""
    await channel.declare_exchange(
        EVENTS_EXCHANGE_NAME, ExchangeType.TOPIC, durable=True
    )


async def test_declare_topology_creates_dlx_main_queue_retry_stages_and_dlq(
    channel: AbstractChannel,
) -> None:
    await declare_topology(channel, SERVICE_NAME)

    # Редекларация с теми же type/durable/arguments проходит без исключения,
    # только если брокер реально хранит именно эти параметры — расхождение
    # бросило бы 406 PRECONDITION_FAILED. Так проверяются "типы/аргументы"
    # объявленных объектов без обращения к management API.
    await channel.declare_exchange(DLX_EXCHANGE_NAME, ExchangeType.DIRECT, durable=True)
    await channel.declare_queue(
        MAIN_QUEUE_NAME,
        durable=True,
        arguments={
            "x-queue-type": "quorum",
            "x-dead-letter-exchange": DLX_EXCHANGE_NAME,
            "x-dead-letter-routing-key": MAIN_QUEUE_NAME,
        },
    )
    for suffix, ttl_ms in RETRY_STAGE_TTL_MS.items():
        await channel.declare_queue(
            f"{MAIN_QUEUE_NAME}.{suffix}",
            durable=True,
            arguments={
                "x-dead-letter-exchange": "",
                "x-dead-letter-routing-key": MAIN_QUEUE_NAME,
                "x-message-ttl": ttl_ms,
            },
        )
    await channel.declare_queue(DLQ_NAME, durable=True)


async def test_declare_topology_is_idempotent(channel: AbstractChannel) -> None:
    await declare_topology(channel, SERVICE_NAME)

    # Повторный вызов с теми же параметрами (например, рестарт процесса) не
    # должен бросить PRECONDITION_FAILED и не должен создать дублей.
    await declare_topology(channel, SERVICE_NAME)


async def test_main_queue_receives_event_matching_wildcard_binding(
    channel: AbstractChannel,
) -> None:
    main_queue = await declare_topology(channel, SERVICE_NAME)
    events_exchange = await channel.get_exchange(EVENTS_EXCHANGE_NAME)

    confirmation = await events_exchange.publish(
        aio_pika.Message(body=b'{"user_id": 1}'),
        routing_key="user.registered.v1",
    )
    assert confirmation is not None

    incoming = await main_queue.get(fail=True)
    await incoming.ack()

    assert incoming.body == b'{"user_id": 1}'
