"""Product-lifecycle консьюмер inventory-worker (issue #367, по образцу
catalog's test_worker.py) — real Postgres + real RabbitMQ. Покрывает оба
уровня идемпотентности (архитектурный бриф #367, риск 2): повторная
доставка того же `message_id` блокируется на `processed_messages`-гейте,
а повторная доставка с ДРУГИМ `message_id` для того же `product_id`
блокируется естественной PK-идемпотентностью репозитория."""

import asyncio
import json
import uuid

import aio_pika
import pytest
import pytest_asyncio
from aio_pika import ExchangeType
from aio_pika.abc import AbstractChannel
from kernel_platform.consumer import consume
from kernel_platform.outbox.settings import EVENTS_EXCHANGE_NAME
from kernel_platform.topology import declare_topology
from sqlalchemy import func, select, text
from sqlalchemy.ext.asyncio import AsyncEngine, AsyncSession, async_sessionmaker

from api.worker import QUEUE_NAME, build_product_event_handler
from infrastructure.db.entity_configurations.models import InventoryModel
from infrastructure.db.processed_messages import ProcessedMessage

pytestmark = pytest.mark.asyncio(loop_scope="session")

SERVICE_NAME = "inventory"


@pytest_asyncio.fixture(loop_scope="session")
async def worker_session_factory(
    db_engine: AsyncEngine,
) -> async_sessionmaker[AsyncSession]:
    async with db_engine.begin() as connection:
        await connection.execute(text("TRUNCATE processed_messages, inventory"))
    return async_sessionmaker(db_engine, expire_on_commit=False)


async def _publish_product_created(
    channel: AbstractChannel, *, message_id: int, product_id: uuid.UUID
) -> None:
    exchange = await channel.get_exchange(EVENTS_EXCHANGE_NAME)
    await exchange.publish(
        aio_pika.Message(
            body=json.dumps(
                {"product_id": str(product_id), "name": "Товар", "price": 10.0}
            ).encode(),
            message_id=str(message_id),
            type="product.created.v2",
        ),
        routing_key="product.created.v2",
    )


async def _wait_for_inventory_row(
    session_factory: async_sessionmaker[AsyncSession], product_id: uuid.UUID
) -> InventoryModel:
    async def _find() -> InventoryModel | None:
        async with session_factory() as session:
            return await session.get(InventoryModel, product_id)

    for _ in range(100):
        row = await _find()
        if row is not None:
            return row
        await asyncio.sleep(0.05)
    raise AssertionError("inventory row was not created within the timeout")


async def test_worker_creates_zero_inventory_row_idempotently_on_redelivery(
    channel: AbstractChannel,
    worker_session_factory: async_sessionmaker[AsyncSession],
) -> None:
    await channel.declare_exchange(
        EVENTS_EXCHANGE_NAME, ExchangeType.TOPIC, durable=True
    )
    queue = await declare_topology(
        channel,
        service_name=SERVICE_NAME,
        queue_name=QUEUE_NAME,
        routing_keys=("product.created.v2",),
    )
    await queue.purge()
    handler = build_product_event_handler(worker_session_factory)
    consumer_tag = await consume(queue, handler, prefetch_count=1)
    product_id = uuid.uuid4()

    try:
        await _publish_product_created(channel, message_id=301, product_id=product_id)
        row = await _wait_for_inventory_row(worker_session_factory, product_id)
        assert row.quantity == 0

        # Redeliver the exact same outbox message_id — simulates at-least-once
        # broker redelivery. Must not create a second row.
        await _publish_product_created(channel, message_id=301, product_id=product_id)
        await asyncio.sleep(0.2)

        async with worker_session_factory() as session:
            row_count = await session.scalar(
                select(func.count())
                .select_from(InventoryModel)
                .where(InventoryModel.product_id == product_id)
            )
            processed_count_301 = await session.scalar(
                select(func.count())
                .select_from(ProcessedMessage)
                .where(ProcessedMessage.message_id == 301)
            )
        assert row_count == 1
        assert processed_count_301 == 1

        # A DIFFERENT message_id for the same product exercises the second,
        # natural-PK idempotency layer: the inbox gate alone would let this
        # one through (new message_id), but ON CONFLICT DO NOTHING on the
        # inventory PK (product_id) still guards against a second row.
        await _publish_product_created(channel, message_id=302, product_id=product_id)
        await asyncio.sleep(0.2)

        async with worker_session_factory() as session:
            row_count_after_second_message_id = await session.scalar(
                select(func.count())
                .select_from(InventoryModel)
                .where(InventoryModel.product_id == product_id)
            )
            processed_count_302 = await session.scalar(
                select(func.count())
                .select_from(ProcessedMessage)
                .where(ProcessedMessage.message_id == 302)
            )
        assert row_count_after_second_message_id == 1
        assert processed_count_302 == 1
    finally:
        await queue.cancel(consumer_tag)
