"""RabbitMQ boundary tests for the search projection worker."""

import aio_pika
import pytest
from aio_pika import ExchangeType
from aio_pika.abc import AbstractChannel
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
