# ruff: noqa: E501
import asyncio

import aio_pika
import pytest
from aio_pika.abc import AbstractChannel, AbstractIncomingMessage, HeadersType

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

# Ступени лестницы для этих тестов сжаты до сотен миллисекунд (issue #110,
# AC "TTL в тесте можно временно уменьшить конфигурацией") — реальные
# 5с/30с/2м брокера сделали бы прогон четырёх попыток минутным.
LADDER_SERVICE_NAME = "kernel-consumer-ladder-test"
LADDER_MAIN_QUEUE_NAME = f"{LADDER_SERVICE_NAME}.user-events"
LADDER_DLQ_NAME = f"{LADDER_MAIN_QUEUE_NAME}.dlq"
LADDER_RETRY_STAGE_TTL_MS = {"retry.5s": 100, "retry.30s": 100, "retry.2m": 100}


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


async def test_consume_routes_message_to_first_retry_stage_on_first_failure(
    channel: AbstractChannel,
) -> None:
    """Начиная с issue #110 первая неудача больше не уходит в DLQ напрямую —
    сообщение маршрутизируется в первую ступень лестницы (`retry.5s`), а
    исходная доставка `ack`'ается, не `reject`'ается. Прямой путь до DLQ
    (все три ступени исчерпаны) проверяют тесты лестницы ниже."""
    main_queue = await declare_topology(channel, SERVICE_NAME)

    async def handler(_message: AbstractIncomingMessage) -> None:
        raise ValueError("boom")

    consumer_tag = await consume(main_queue, handler)
    try:
        retry_5s = await channel.get_queue(f"{MAIN_QUEUE_NAME}.retry.5s")
        routed_to_stage: asyncio.Queue[AbstractIncomingMessage] = asyncio.Queue()

        async def on_routed_to_stage(message: AbstractIncomingMessage) -> None:
            await message.ack()
            await routed_to_stage.put(message)

        # `Queue.get(fail=True)` — это одноразовый `basic_get`, не ожидание:
        # он мгновенно проверяет очередь и не ждёт, пока брокер домаршрутизирует
        # сообщение (гонка, воспроизводимая на медленном CI-раннере).
        # Живой консьюмер получает сообщение push'ем, как только оно там
        # появится, сколько бы это ни заняло.
        stage_consumer_tag = await retry_5s.consume(on_routed_to_stage)
        try:
            await _publish_event(channel, b'{"user_id": 2}')
            incoming = await asyncio.wait_for(routed_to_stage.get(), timeout=5)

            assert incoming.body == b'{"user_id": 2}'
            dlq = await channel.get_queue(DLQ_NAME)
            assert await dlq.get(fail=False, timeout=1) is None
        finally:
            await retry_5s.cancel(stage_consumer_tag)
    finally:
        await main_queue.cancel(consumer_tag)


async def test_consume_routes_message_to_second_retry_stage_after_second_failure(
    channel: AbstractChannel,
) -> None:
    """Вторая неудача (после того как первая ступень по TTL вернула
    сообщение в основную очередь) уходит именно в `retry.30s` — прямая
    проверка второй ступени, не только вывод по счётчику попыток."""
    main_queue = await declare_topology(
        channel, LADDER_SERVICE_NAME, retry_stage_ttl_ms=LADDER_RETRY_STAGE_TTL_MS
    )

    async def handler(_message: AbstractIncomingMessage) -> None:
        raise ValueError("boom")

    consumer_tag = await consume(main_queue, handler)
    try:
        retry_30s = await channel.get_queue(f"{LADDER_MAIN_QUEUE_NAME}.retry.30s")
        routed_to_stage: asyncio.Queue[AbstractIncomingMessage] = asyncio.Queue()

        async def on_routed_to_stage(message: AbstractIncomingMessage) -> None:
            await message.ack()
            await routed_to_stage.put(message)

        stage_consumer_tag = await retry_30s.consume(on_routed_to_stage)
        try:
            await _publish_event(channel, b'{"user_id": 5}')
            incoming = await asyncio.wait_for(routed_to_stage.get(), timeout=5)

            assert incoming.body == b'{"user_id": 5}'
        finally:
            await retry_30s.cancel(stage_consumer_tag)
    finally:
        await main_queue.cancel(consumer_tag)


async def test_consume_routes_message_to_third_retry_stage_after_third_failure(
    channel: AbstractChannel,
) -> None:
    """Третья неудача (после того как первая и вторая ступени по TTL вернули
    сообщение в основную очередь) уходит именно в `retry.2m` — прямая
    проверка третьей ступени (issue #110)."""
    main_queue = await declare_topology(
        channel, LADDER_SERVICE_NAME, retry_stage_ttl_ms=LADDER_RETRY_STAGE_TTL_MS
    )

    async def handler(_message: AbstractIncomingMessage) -> None:
        raise ValueError("boom")

    consumer_tag = await consume(main_queue, handler)
    try:
        retry_2m = await channel.get_queue(f"{LADDER_MAIN_QUEUE_NAME}.retry.2m")
        routed_to_stage: asyncio.Queue[AbstractIncomingMessage] = asyncio.Queue()

        async def on_routed_to_stage(message: AbstractIncomingMessage) -> None:
            await message.ack()
            await routed_to_stage.put(message)

        stage_consumer_tag = await retry_2m.consume(on_routed_to_stage)
        try:
            await _publish_event(channel, b'{"user_id": 6}')
            incoming = await asyncio.wait_for(routed_to_stage.get(), timeout=5)

            assert incoming.body == b'{"user_id": 6}'
        finally:
            await retry_2m.cancel(stage_consumer_tag)
    finally:
        await main_queue.cancel(consumer_tag)


async def test_consume_x_death_reflects_only_the_most_recent_stage(
    channel: AbstractChannel,
) -> None:
    """Документирует эмпирически проверенное поведение брокера (см. docstring
    `_next_stage_index` в `consumer.py`): при очередном TTL-дед-леттеринге
    RabbitMQ заменяет `x-death` одной записью о последней пройденной
    ступени, а не накапливает записи по всем пройденным ступеням сразу —
    поэтому подсчёт следующей ступени не может опираться на длину/сумму
    массива, только на то, какая ступень там названа последней."""
    main_queue = await declare_topology(
        channel, LADDER_SERVICE_NAME, retry_stage_ttl_ms=LADDER_RETRY_STAGE_TTL_MS
    )
    seen_x_death: list[HeadersType] = []
    handled = asyncio.Event()

    async def handler(message: AbstractIncomingMessage) -> None:
        seen_x_death.append(message.headers)
        if len(seen_x_death) < 3:
            raise ValueError("boom")
        handled.set()

    consumer_tag = await consume(main_queue, handler)
    try:
        await _publish_event(channel, b'{"user_id": 7}')
        await asyncio.wait_for(handled.wait(), timeout=5)

        assert seen_x_death[0].get("x-death") is None

        def _single_stage_entry(headers: HeadersType, stage_queue_name: str) -> None:
            x_death = headers.get("x-death")
            assert isinstance(x_death, list)
            assert len(x_death) == 1
            entry = x_death[0]
            assert isinstance(entry, dict)
            assert entry["queue"] == stage_queue_name
            assert entry["count"] == 1
            assert entry["reason"] == "expired"

        _single_stage_entry(seen_x_death[1], f"{LADDER_MAIN_QUEUE_NAME}.retry.5s")
        _single_stage_entry(seen_x_death[2], f"{LADDER_MAIN_QUEUE_NAME}.retry.30s")
    finally:
        await main_queue.cancel(consumer_tag)


async def test_consume_escalates_through_all_stages_then_routes_to_dlq(
    channel: AbstractChannel,
) -> None:
    main_queue = await declare_topology(
        channel, LADDER_SERVICE_NAME, retry_stage_ttl_ms=LADDER_RETRY_STAGE_TTL_MS
    )
    attempts: list[int] = []

    async def handler(_message: AbstractIncomingMessage) -> None:
        attempts.append(1)
        raise ValueError("boom")

    consumer_tag = await consume(main_queue, handler)
    try:
        dlq = await channel.get_queue(LADDER_DLQ_NAME)
        dead_lettered: asyncio.Queue[AbstractIncomingMessage] = asyncio.Queue()

        async def on_dead_lettered(message: AbstractIncomingMessage) -> None:
            await message.ack()
            await dead_lettered.put(message)

        dlq_consumer_tag = await dlq.consume(on_dead_lettered)
        try:
            await _publish_event(channel, b'{"user_id": 3}')
            incoming = await asyncio.wait_for(dead_lettered.get(), timeout=10)

            assert incoming.body == b'{"user_id": 3}'
            # Ровно 4 попытки: первая доставка + по одной на каждую из трёх
            # ступеней лестницы, прежде чем сообщение уходит в DLQ.
            assert len(attempts) == 4
        finally:
            await dlq.cancel(dlq_consumer_tag)
    finally:
        await main_queue.cancel(consumer_tag)


async def test_consume_stops_escalating_once_handler_succeeds(
    channel: AbstractChannel,
) -> None:
    main_queue = await declare_topology(
        channel, LADDER_SERVICE_NAME, retry_stage_ttl_ms=LADDER_RETRY_STAGE_TTL_MS
    )
    attempts: list[int] = []
    handled = asyncio.Event()

    async def handler(_message: AbstractIncomingMessage) -> None:
        attempts.append(1)
        if len(attempts) < 3:
            raise ValueError("boom")
        handled.set()

    consumer_tag = await consume(main_queue, handler)
    try:
        await _publish_event(channel, b'{"user_id": 4}')
        await asyncio.wait_for(handled.wait(), timeout=10)

        # Успех на третьей попытке (после двух ступеней) — попыток ровно 3,
        # сообщение не попадает ни в очередь следующей ступени, ни в DLQ.
        assert len(attempts) == 3
        retry_2m = await channel.get_queue(f"{LADDER_MAIN_QUEUE_NAME}.retry.2m")
        assert await retry_2m.get(fail=False, timeout=1) is None
        dlq = await channel.get_queue(LADDER_DLQ_NAME)
        assert await dlq.get(fail=False, timeout=1) is None
    finally:
        await main_queue.cancel(consumer_tag)
