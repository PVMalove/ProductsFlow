import asyncio

import aio_pika
import pytest
from aio_pika.abc import AbstractChannel, AbstractIncomingMessage
from kernel_platform.consumer import consume
from kernel_platform.outbox.publisher import EVENTS_EXCHANGE_NAME
from kernel_platform.topology import declare_topology

# amqp_connection/channel/events_exchange_exists (conftest.py) —
# module/session-scoped, bound к session-scoped event loop; см.
# test_topology.py.
pytestmark = pytest.mark.asyncio(loop_scope="session")

SERVICE_NAME = "kernel-consumer-test"
MAIN_QUEUE_NAME = f"{SERVICE_NAME}.user-events"
DLQ_NAME = f"{MAIN_QUEUE_NAME}.dlq"


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
        dlq = await channel.get_queue(DLQ_NAME)
        dead_lettered: asyncio.Queue[AbstractIncomingMessage] = asyncio.Queue()

        async def on_dead_lettered(message: AbstractIncomingMessage) -> None:
            await message.ack()
            await dead_lettered.put(message)

        # `Queue.get(fail=True)` — это одноразовый `basic_get`, не ожидание:
        # он мгновенно проверяет очередь и не ждёт, пока брокер домаршрутизирует
        # `reject` в DLQ (гонка, воспроизводимая на медленном CI-раннере).
        # Живой консьюмер получает сообщение push'ем, как только оно там
        # появится, сколько бы это ни заняло.
        dlq_consumer_tag = await dlq.consume(on_dead_lettered)
        try:
            await _publish_event(channel, b'{"user_id": 2}')
            incoming = await asyncio.wait_for(dead_lettered.get(), timeout=5)

            assert incoming.body == b'{"user_id": 2}'
        finally:
            await dlq.cancel(dlq_consumer_tag)
    finally:
        await main_queue.cancel(consumer_tag)
