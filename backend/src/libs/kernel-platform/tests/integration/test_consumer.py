import asyncio
from collections.abc import AsyncIterator

import aio_pika
import pytest
import pytest_asyncio
from aio_pika.abc import (
    AbstractChannel,
    AbstractIncomingMessage,
    AbstractRobustConnection,
)
from kernel_platform.consumer import consume
from kernel_platform.outbox.publisher import EVENTS_EXCHANGE_NAME
from kernel_platform.topology import declare_topology

# amqp_connection (conftest.py) — module-scoped, bound к session-scoped
# event loop; см. test_topology.py.
pytestmark = pytest.mark.asyncio(loop_scope="session")

SERVICE_NAME = "kernel-consumer-test"
MAIN_QUEUE_NAME = f"{SERVICE_NAME}.user-events"
DLQ_NAME = f"{MAIN_QUEUE_NAME}.dlq"


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
    """Симулирует объявление identity-service при своём старте (ADR 0015)."""
    await channel.declare_exchange(
        EVENTS_EXCHANGE_NAME, aio_pika.ExchangeType.TOPIC, durable=True
    )


async def _publish_event(channel: AbstractChannel, body: bytes) -> None:
    events_exchange = await channel.get_exchange(EVENTS_EXCHANGE_NAME)
    await events_exchange.publish(
        aio_pika.Message(body=body), routing_key="user.registered.v1"
    )


async def test_consume_acks_message_on_successful_handling(
    channel: AbstractChannel,
) -> None:
    main_queue = await declare_topology(channel, SERVICE_NAME)
    handled = asyncio.Event()

    async def handler(_message: AbstractIncomingMessage) -> None:
        handled.set()

    consumer_tag = await consume(main_queue, handler)
    try:
        await _publish_event(channel, b'{"user_id": 1}')
        await asyncio.wait_for(handled.wait(), timeout=5)

        # Успешно обработанное сообщение не остаётся в основной очереди и не
        # попадает в DLQ.
        assert await main_queue.get(fail=False, timeout=1) is None
        dlq = await channel.get_queue(DLQ_NAME)
        assert await dlq.get(fail=False, timeout=1) is None
    finally:
        await main_queue.cancel(consumer_tag)


async def test_consume_routes_message_to_dlq_when_handler_raises(
    channel: AbstractChannel,
) -> None:
    main_queue = await declare_topology(channel, SERVICE_NAME)

    async def handler(_message: AbstractIncomingMessage) -> None:
        raise ValueError("boom")

    consumer_tag = await consume(main_queue, handler)
    try:
        await _publish_event(channel, b'{"user_id": 2}')

        dlq = await channel.get_queue(DLQ_NAME)
        incoming = await dlq.get(fail=True, timeout=5)
        await incoming.ack()

        assert incoming.body == b'{"user_id": 2}'
    finally:
        await main_queue.cancel(consumer_tag)
