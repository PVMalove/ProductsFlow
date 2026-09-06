"""RabbitMQ boundary tests for the search projection worker."""

import asyncio

import aio_pika
import pytest
from aio_pika import ExchangeType
from aio_pika.abc import AbstractChannel, AbstractIncomingMessage
from kernel_platform.consumer import consume
from kernel_platform.outbox.settings import EVENTS_EXCHANGE_NAME
from kernel_platform.topology import DLX_EXCHANGE_NAME, RETRY_STAGE_TTL_MS

from api.search_worker import SEARCH_EVENTS_QUEUE_NAME, declare_search_events_queue

pytestmark = pytest.mark.asyncio(loop_scope="session")


async def test_search_queue_routes_tombstones_and_declares_bounded_retry_dlq(
    channel: AbstractChannel,
) -> None:
    queue = await declare_search_events_queue(channel)
    await queue.purge()
    events = await channel.get_exchange(EVENTS_EXCHANGE_NAME)

    await events.publish(
        aio_pika.Message(body=b'{"product_id":"00000000-0000-0000-0000-000000000001"}'),
        routing_key="product.deleted.v2",
    )
    incoming = await queue.get(fail=True)
    await incoming.ack()

    assert incoming.routing_key == "product.deleted.v2"
    await channel.declare_exchange(DLX_EXCHANGE_NAME, ExchangeType.DIRECT, durable=True)
    await channel.declare_queue(
        SEARCH_EVENTS_QUEUE_NAME,
        durable=True,
        arguments={
            "x-queue-type": "quorum",
            "x-dead-letter-exchange": DLX_EXCHANGE_NAME,
            "x-dead-letter-routing-key": SEARCH_EVENTS_QUEUE_NAME,
        },
    )
    for suffix, ttl_ms in RETRY_STAGE_TTL_MS.items():
        await channel.declare_queue(
            f"{SEARCH_EVENTS_QUEUE_NAME}.{suffix}",
            durable=True,
            arguments={
                "x-dead-letter-exchange": "",
                "x-dead-letter-routing-key": SEARCH_EVENTS_QUEUE_NAME,
                "x-message-ttl": ttl_ms,
            },
        )
    await channel.declare_queue(f"{SEARCH_EVENTS_QUEUE_NAME}.dlq", durable=True)


async def test_poison_search_message_reaches_dlq_without_blocking_next_message(
    channel: AbstractChannel,
) -> None:
    fast_retry = {suffix: 10 for suffix in RETRY_STAGE_TTL_MS}
    queue_name = "catalog.search-events.poison-test"
    queue = await declare_search_events_queue(
        channel,
        queue_name=queue_name,
        retry_stage_ttl_ms=fast_retry,
    )
    dlq = await channel.get_queue(f"{queue_name}.dlq")
    await queue.purge()
    await dlq.purge()
    processed = asyncio.Event()

    async def handler(message: AbstractIncomingMessage) -> None:
        if message.body == b"poison":
            raise ValueError("unparseable event")
        processed.set()

    consumer_tag = await consume(queue, handler)
    events = await channel.get_exchange(EVENTS_EXCHANGE_NAME)
    try:
        await events.publish(
            aio_pika.Message(body=b"poison"), routing_key="product.deleted.v2"
        )
        await events.publish(
            aio_pika.Message(body=b"healthy"), routing_key="product.deleted.v2"
        )
        await asyncio.wait_for(processed.wait(), timeout=2)

        for _ in range(100):
            message = await dlq.get(fail=False)
            if message is not None:
                assert message.body == b"poison"
                await message.ack()
                break
            await asyncio.sleep(0.02)
        else:
            raise AssertionError("poison message did not reach the DLQ")
    finally:
        await queue.cancel(consumer_tag)
