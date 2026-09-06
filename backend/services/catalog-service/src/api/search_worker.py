import asyncio
import json
import logging
import uuid
from collections.abc import Awaitable, Callable
from datetime import UTC, datetime

import aio_pika
from aio_pika.abc import AbstractChannel, AbstractIncomingMessage, AbstractQueue
from kernel_platform.consumer import consume
from kernel_platform.topology import declare_topology
from prometheus_client import start_http_server
from sqlalchemy.ext.asyncio import async_sessionmaker, create_async_engine

from application.ports import (
    OwnerSearchState,
    OwnerSearchStateStore,
    ProductSearchIndexer,
)
from application.search_snapshot import ProductSearchSnapshot, ProductSearchTombstone
from core.settings import settings
from infrastructure.db.search_owner_state import SqlOwnerSearchStateStore
from infrastructure.metrics.search_metrics import (
    SEARCH_INDEXING_LAG,
    PendingEventTracker,
    poll_dlq_depth,
)
from infrastructure.search.opensearch import OpenSearchProductSearch

logger = logging.getLogger(__name__)

PRODUCT_EVENT_TYPES = frozenset(
    {
        "product.created.v2",
        "product.updated.v2",
        "product.activated.v2",
        "product.deactivated.v2",
        "product.deleted.v2",
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


def _parse_product_tombstone(body: bytes) -> ProductSearchTombstone:
    try:
        payload: object = json.loads(body)
    except (UnicodeDecodeError, json.JSONDecodeError) as exc:
        raise ValueError("Product tombstone payload is not valid JSON") from exc
    if not isinstance(payload, dict):
        raise ValueError("Product tombstone payload must be a JSON object")
    try:
        product_id = uuid.UUID(str(payload["product_id"]))
        user_id = uuid.UUID(str(payload["user_id"]))
        search_revision = payload["search_revision"]
    except (KeyError, TypeError, ValueError) as exc:
        raise ValueError("Product tombstone payload is incomplete") from exc
    if (
        isinstance(search_revision, bool)
        or not isinstance(search_revision, int)
        or search_revision < 1
    ):
        raise ValueError("Product tombstone payload has invalid search_revision")
    return ProductSearchTombstone(
        product_id=product_id,
        user_id=user_id,
        search_revision=search_revision,
    )


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


async def handle_product_tombstone(
    message: AbstractIncomingMessage, indexer: ProductSearchIndexer
) -> None:
    _event_type(message)
    tombstone = _parse_product_tombstone(message.body)
    await indexer.delete(tombstone)
    logger.info(
        "catalog-search-worker: deleted product %s at revision %s",
        tombstone.product_id,
        tombstone.search_revision,
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
    if event_type == "product.deleted.v2":
        await handle_product_tombstone(message, indexer)
    elif event_type in PRODUCT_EVENT_TYPES:
        await handle_product_event(message, indexer, owner_states)
    else:
        await handle_owner_event(message, indexer, owner_states)


def _tracking_key(message: AbstractIncomingMessage) -> tuple[int, datetime] | None:
    """Возвращает `(message_id, occurred_at)` для отслеживания в
    `PendingEventTracker` (issue #293), либо `None`, если у сообщения нет
    того, что для этого нужно — тогда обработка идёт как обычно, просто без
    метрик наблюдаемости для этого конкретного сообщения."""
    try:
        message_id = _message_id(message)
    except ValueError:
        return None
    occurred_at = message.timestamp
    if occurred_at is None:
        return None
    if occurred_at.tzinfo is None:
        occurred_at = occurred_at.replace(tzinfo=UTC)
    return message_id, occurred_at


def build_search_event_handler(
    indexer: ProductSearchIndexer,
    owner_states: OwnerSearchStateStore,
    tracker: PendingEventTracker,
) -> Callable[[AbstractIncomingMessage], Awaitable[None]]:
    async def _handler(message: AbstractIncomingMessage) -> None:
        tracking_key = _tracking_key(message)
        if tracking_key is not None:
            await tracker.mark_received(*tracking_key)
        try:
            await handle_search_event(message, indexer, owner_states)
        finally:
            if tracking_key is not None:
                await tracker.mark_done(tracking_key[0])
        if tracking_key is not None and _event_type(message) in PRODUCT_EVENT_TYPES:
            _, occurred_at = tracking_key
            lag_seconds = (datetime.now(UTC) - occurred_at).total_seconds()
            SEARCH_INDEXING_LAG.observe(max(lag_seconds, 0.0))

    return _handler


SEARCH_EVENTS_QUEUE_NAME = "catalog.search-events"


async def declare_search_events_queue(channel: AbstractChannel) -> AbstractQueue:
    """Declare the search consumer's retry ladder and its DLQ.

    The shared consumer acknowledges a failed message after forwarding it to
    a bounded TTL retry stage.  Once the stages are exhausted, RabbitMQ sends
    it to ``catalog.search-events.dlq``; later valid deliveries continue on
    the main queue instead of being blocked by the poison message.
    """
    return await declare_topology(
        channel,
        service_name="catalog",
        queue_name=SEARCH_EVENTS_QUEUE_NAME,
        routing_keys=("product.*.v2", *OWNER_EVENT_TYPES),
    )


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
    tracker = PendingEventTracker()
    start_http_server(settings.catalog_search_worker_metrics_port)
    dlq_poll_task = asyncio.create_task(
        poll_dlq_depth(
            management_url=settings.catalog_rabbitmq_management_url,
            username=settings.catalog_rabbitmq_management_user,
            password=settings.catalog_rabbitmq_management_password,
            queue_name=SEARCH_EVENTS_QUEUE_NAME,
            interval_seconds=settings.catalog_search_dlq_poll_interval_seconds,
        )
    )
    try:
        async with connection:
            channel = await connection.channel()
            queue = await declare_search_events_queue(channel)
            await consume(
                queue, build_search_event_handler(indexer, owner_states, tracker)
            )
            logger.info("catalog-search-worker: search event consumer started")
            await asyncio.Future()
    finally:
        dlq_poll_task.cancel()
        await indexer.close()
        await engine.dispose()


if __name__ == "__main__":
    asyncio.run(main())
