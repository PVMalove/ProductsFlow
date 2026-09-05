import asyncio
import json
import logging
import uuid
from collections.abc import Awaitable, Callable

import aio_pika
from aio_pika.abc import AbstractChannel, AbstractIncomingMessage, AbstractQueue
from kernel_platform.consumer import consume
from kernel_platform.outbox.settings import EVENTS_EXCHANGE_NAME

from application.ports import ProductSearchIndexer
from application.search_snapshot import ProductSearchSnapshot
from core.settings import settings
from infrastructure.search.opensearch import OpenSearchProductSearch

logger = logging.getLogger(__name__)

PRODUCT_EVENT_TYPES = frozenset(
    {
        "product.created.v2",
        "product.updated.v2",
        "product.activated.v2",
        "product.deactivated.v2",
    }
)


def _event_type(message: AbstractIncomingMessage) -> str:
    event_type = message.type or message.routing_key
    if event_type not in PRODUCT_EVENT_TYPES:
        raise ValueError(f"Unsupported product event type: {event_type!r}")
    return event_type


def _parse_product_snapshot(body: bytes) -> ProductSearchSnapshot:
    try:
        payload: object = json.loads(body)
    except (UnicodeDecodeError, json.JSONDecodeError) as exc:
        raise ValueError("Product event payload is not valid JSON") from exc
    if not isinstance(payload, dict):
        raise ValueError("Product event payload must be a JSON object")
    try:
        product_id = uuid.UUID(str(payload["product_id"]))
        user_id = uuid.UUID(str(payload["user_id"]))
        name = payload["name"]
        description = payload["description"]
        category = payload["category"]
        price = payload["price"]
        is_active = payload["is_active"]
        search_revision = payload["search_revision"]
    except (KeyError, TypeError, ValueError) as exc:
        raise ValueError("Product event payload is incomplete") from exc
    if (
        not isinstance(name, str)
        or not isinstance(description, str)
        or not isinstance(category, str)
        or isinstance(price, bool)
        or not isinstance(price, (int, float))
        or not isinstance(is_active, bool)
        or isinstance(search_revision, bool)
        or not isinstance(search_revision, int)
        or search_revision < 1
    ):
        raise ValueError("Product event payload has invalid field types")
    return ProductSearchSnapshot(
        product_id=product_id,
        user_id=user_id,
        name=name,
        description=description,
        category=category,
        price=float(price),
        is_active=is_active,
        search_revision=search_revision,
    )


async def handle_product_event(
    message: AbstractIncomingMessage, indexer: ProductSearchIndexer
) -> None:
    event_type = _event_type(message)
    snapshot = _parse_product_snapshot(message.body)
    await indexer.index(snapshot)
    logger.info(
        "catalog-search-worker: indexed %s for product %s at revision %s",
        event_type,
        snapshot.product_id,
        snapshot.search_revision,
    )


def build_product_event_handler(
    indexer: ProductSearchIndexer,
) -> Callable[[AbstractIncomingMessage], Awaitable[None]]:
    async def _handler(message: AbstractIncomingMessage) -> None:
        await handle_product_event(message, indexer)

    return _handler


async def declare_product_search_queue(channel: AbstractChannel) -> AbstractQueue:
    exchange = await channel.get_exchange(EVENTS_EXCHANGE_NAME, ensure=True)
    queue = await channel.declare_queue("catalog.search-events", durable=True)
    await queue.bind(exchange, routing_key="product.*.v2")
    return queue


async def main() -> None:
    """Runs the dedicated Catalog Product-to-OpenSearch projection worker."""
    connection = await aio_pika.connect_robust(settings.catalog_amqp_url)
    indexer = OpenSearchProductSearch(
        base_url=settings.catalog_opensearch_url,
        index_name=settings.catalog_search_index_name,
    )
    try:
        async with connection:
            channel = await connection.channel()
            queue = await declare_product_search_queue(channel)
            await consume(queue, build_product_event_handler(indexer))
            logger.info("catalog-search-worker: product snapshot consumer started")
            await asyncio.Future()
    finally:
        await indexer.close()


if __name__ == "__main__":
    asyncio.run(main())
