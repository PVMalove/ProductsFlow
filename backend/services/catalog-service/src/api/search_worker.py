import asyncio
import json
import logging
import uuid
from collections.abc import Awaitable, Callable
from datetime import datetime

import aio_pika
from aio_pika.abc import AbstractChannel, AbstractIncomingMessage, AbstractQueue
from kernel_platform.consumer import consume
from kernel_platform.outbox.settings import EVENTS_EXCHANGE_NAME
from sqlalchemy.ext.asyncio import async_sessionmaker, create_async_engine

from application.ports import (
    OwnerSearchState,
    OwnerSearchStateStore,
    ProductSearchIndexer,
)
from application.search_snapshot import ProductSearchSnapshot
from core.settings import settings
from infrastructure.db.search_owner_state import SqlOwnerSearchStateStore
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

# Deliberately excludes `user.role_changed.v1`/`user.password_changed.v1` —
# neither affects search visibility.
OWNER_EVENT_TYPES = frozenset(
    {
        "user.registered.v1",
        "user.activated.v1",
        "user.deactivated.v1",
        "user.deleted.v1",
    }
)

_SEARCH_EVENT_TYPES = PRODUCT_EVENT_TYPES | OWNER_EVENT_TYPES

# A brand-new owner is active but never receives an explicit
# `user.activated.v1` (that event only fires on reactivation from a prior
# deactivation) — without seeding Owner Search State from registration too,
# a new owner's first products would stay hidden forever under
# deny-by-default.
_ACTIVE_OWNER_EVENT_TYPES = frozenset({"user.registered.v1", "user.activated.v1"})


def _event_type(message: AbstractIncomingMessage) -> str:
    event_type = message.type or message.routing_key
    if event_type not in _SEARCH_EVENT_TYPES:
        raise ValueError(f"Unsupported search worker event type: {event_type!r}")
    return event_type


def _message_id(message: AbstractIncomingMessage) -> int:
    raw_message_id = message.message_id
    try:
        message_id = int(raw_message_id) if raw_message_id is not None else 0
    except (TypeError, ValueError) as exc:
        raise ValueError(f"Invalid outbox message id: {raw_message_id!r}") from exc
    if message_id <= 0:
        raise ValueError(f"Invalid outbox message id: {raw_message_id!r}")
    return message_id


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
        created_at_raw = payload["created_at"]
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
        or not isinstance(created_at_raw, str)
    ):
        raise ValueError("Product event payload has invalid field types")
    try:
        created_at = datetime.fromisoformat(created_at_raw)
    except ValueError as exc:
        raise ValueError("Product event payload has an invalid created_at") from exc
    return ProductSearchSnapshot(
        product_id=product_id,
        user_id=user_id,
        name=name,
        description=description,
        category=category,
        price=float(price),
        is_active=is_active,
        search_revision=search_revision,
        created_at=created_at,
    )


def _parse_owner_user_id(body: bytes) -> uuid.UUID:
    try:
        payload: object = json.loads(body)
    except (UnicodeDecodeError, json.JSONDecodeError) as exc:
        raise ValueError("Owner event payload is not valid JSON") from exc
    if not isinstance(payload, dict):
        raise ValueError("Owner event payload must be a JSON object")
    raw_user_id = payload.get("user_id", payload.get("id"))
    try:
        return uuid.UUID(str(raw_user_id))
    except (AttributeError, ValueError) as exc:
        raise ValueError(f"Invalid owner user id: {raw_user_id!r}") from exc


async def handle_product_event(
    message: AbstractIncomingMessage,
    indexer: ProductSearchIndexer,
    owner_states: OwnerSearchStateStore,
) -> None:
    """Always re-derives `owner_is_active` from local Owner Search State
    rather than the incoming event (which never carries it) — otherwise a
    delayed Product event would silently reset visibility for an already
    hidden owner (issue #288 acceptance criterion 3)."""
    event_type = _event_type(message)
    snapshot = _parse_product_snapshot(message.body)
    owner_state = await owner_states.get(snapshot.user_id)
    owner_is_active = owner_state.is_active if owner_state is not None else False
    await indexer.index(snapshot, owner_is_active=owner_is_active)
    logger.info(
        "catalog-search-worker: indexed %s for product %s at revision %s "
        "(owner_is_active=%s)",
        event_type,
        snapshot.product_id,
        snapshot.search_revision,
        owner_is_active,
    )


async def handle_owner_event(
    message: AbstractIncomingMessage,
    indexer: ProductSearchIndexer,
    owner_states: OwnerSearchStateStore,
) -> None:
    event_type = _event_type(message)
    user_id = _parse_owner_user_id(message.body)
    message_id = _message_id(message)
    is_active = event_type in _ACTIVE_OWNER_EVENT_TYPES

    applied = await owner_states.upsert(
        OwnerSearchState(
            user_id=user_id, is_active=is_active, last_applied_outbox_id=message_id
        )
    )
    if applied:
        await indexer.set_owner_active(user_id, is_active=is_active)
    logger.info(
        "catalog-search-worker: applied %s for owner %s at outbox version %s "
        "(applied=%s)",
        event_type,
        user_id,
        message_id,
        applied,
    )


async def handle_search_event(
    message: AbstractIncomingMessage,
    indexer: ProductSearchIndexer,
    owner_states: OwnerSearchStateStore,
) -> None:
    event_type = _event_type(message)
    if event_type in PRODUCT_EVENT_TYPES:
        await handle_product_event(message, indexer, owner_states)
    else:
        await handle_owner_event(message, indexer, owner_states)


def build_search_event_handler(
    indexer: ProductSearchIndexer,
    owner_states: OwnerSearchStateStore,
) -> Callable[[AbstractIncomingMessage], Awaitable[None]]:
    async def _handler(message: AbstractIncomingMessage) -> None:
        await handle_search_event(message, indexer, owner_states)

    return _handler


async def declare_search_events_queue(channel: AbstractChannel) -> AbstractQueue:
    exchange = await channel.get_exchange(EVENTS_EXCHANGE_NAME, ensure=True)
    queue = await channel.declare_queue("catalog.search-events", durable=True)
    await queue.bind(exchange, routing_key="product.*.v2")
    # Bound here (not only by identity's own topology) so an owner event
    # published before catalog-search-worker finishes starting isn't lost —
    # same cold-start rationale as `catalog-outbox-worker` pre-declaring this
    # queue for Product events.
    for event_type in OWNER_EVENT_TYPES:
        await queue.bind(exchange, routing_key=event_type)
    return queue


async def main() -> None:
    """Runs the dedicated Catalog Product-to-OpenSearch projection worker."""
    engine = create_async_engine(
        settings.catalog_database_url,
        pool_pre_ping=True,
        pool_size=settings.db_pool_size,
        max_overflow=settings.db_max_overflow,
        pool_recycle=settings.db_pool_recycle,
    )
    session_factory = async_sessionmaker(engine, expire_on_commit=False)
    owner_states = SqlOwnerSearchStateStore(session_factory)
    connection = await aio_pika.connect_robust(settings.catalog_amqp_url)
    indexer = OpenSearchProductSearch(
        base_url=settings.catalog_opensearch_url,
        index_name=settings.catalog_search_index_name,
    )
    try:
        async with connection:
            channel = await connection.channel()
            queue = await declare_search_events_queue(channel)
            await consume(queue, build_search_event_handler(indexer, owner_states))
            logger.info("catalog-search-worker: search event consumer started")
            await asyncio.Future()
    finally:
        await indexer.close()
        await engine.dispose()


if __name__ == "__main__":
    asyncio.run(main())
