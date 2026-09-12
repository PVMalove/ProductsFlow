import asyncio
import json
import logging
import uuid
from collections.abc import Awaitable, Callable

import aio_pika
from aio_pika.abc import AbstractIncomingMessage
from kernel_platform.commands import consume_command
from kernel_platform.consumer import consume
from kernel_platform.topology import declare_command_topology, declare_topology
from observability.tracing import configure_tracing
from sqlalchemy.dialects.postgresql import insert
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine

from api import reservation_sweep
from api.reservation_commands import COMMAND_HANDLERS
from core.settings import settings
from infrastructure.db.inventory_repository import InventoryRepository
from infrastructure.db.processed_messages import ProcessedMessage

logger = logging.getLogger(__name__)

# Только Product lifecycle (issue #367) — Reservation/Allocation/`inventory.*.v1`
# принадлежат более поздним детям эпика #363 (ADR 0016), не этому консьюмеру.
PRODUCT_EVENT_TYPES = frozenset({"product.created.v2"})
# Явный `queue_name` обязателен: дефолт `declare_topology` буквально
# называется `<service>.user-events`, что вводило бы в заблуждение для
# Product-события (архитектурный бриф #367, «Открытый вопрос — разрешение», п.3).
QUEUE_NAME = "inventory.product-events"


def _event_type(message: AbstractIncomingMessage) -> str:
    event_type = message.type or message.routing_key
    if event_type not in PRODUCT_EVENT_TYPES:
        raise ValueError(f"Unsupported product event type: {event_type!r}")
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


def parse_product_created_snapshot(body: bytes) -> uuid.UUID:
    """Парсит `product.created.v2`-payload, толерантно к лишним полям
    снапшота (по образцу catalog-worker's `_parse_user_event_snapshot`) —
    нужен только `product_id`."""
    try:
        payload: object = json.loads(body)
    except (UnicodeDecodeError, json.JSONDecodeError) as exc:
        raise ValueError("Product event payload is not valid JSON") from exc
    if not isinstance(payload, dict):
        raise ValueError("Product event payload must be a JSON object")

    raw_product_id = payload.get("product_id")
    try:
        return uuid.UUID(str(raw_product_id))
    except (AttributeError, ValueError) as exc:
        raise ValueError(f"Invalid product id: {raw_product_id!r}") from exc


async def handle_product_event(
    message: AbstractIncomingMessage,
    session_factory: async_sessionmaker[AsyncSession],
) -> None:
    """Атомарно создаёт нулевую Inventory-запись и фиксирует id обработанного
    сообщения. Идемпотентность двухуровневая (issue #367, риск 2): (a)
    `processed_messages`-гейт по `message_id`, (b) natural PK-идемпотентность
    репозитория (`ON CONFLICT (product_id) DO NOTHING`) — защищает даже от
    дубля с другим `message_id` для того же `product_id`."""
    event_type = _event_type(message)
    message_id = _message_id(message)

    async with session_factory() as session:
        async with session.begin():
            inserted_id = await session.scalar(
                insert(ProcessedMessage)
                .values(message_id=message_id)
                .on_conflict_do_nothing()
                .returning(ProcessedMessage.message_id)
            )
            if inserted_id is None:
                logger.info(
                    "inventory-worker: message %s already processed; skipping",
                    message_id,
                )
                return

            product_id = parse_product_created_snapshot(message.body)
            await InventoryRepository(session).create_zero(product_id)

    logger.info(
        "inventory-worker: applied %s for product %s at outbox message %s",
        event_type,
        product_id,
        message_id,
    )


def build_product_event_handler(
    session_factory: async_sessionmaker[AsyncSession],
) -> Callable[[AbstractIncomingMessage], Awaitable[None]]:
    async def _handler(message: AbstractIncomingMessage) -> None:
        await handle_product_event(message, session_factory)

    return _handler


async def main() -> None:
    """Запускает воркер inventory: Product-lifecycle консьюмер (issue #367),
    reservation command-консьюмеры и TTL-sweep (issue #370, D5 — расширяет
    уже существующий `inventory-worker`-процесс, а не новый контейнер,
    вынужденно из-за write-scope дispatch'а #370; Product-lifecycle код выше
    не тронут)."""
    configure_tracing("inventory-worker")
    engine = create_async_engine(
        settings.inventory_database_url,
        pool_pre_ping=True,
        pool_size=settings.db_pool_size,
        max_overflow=settings.db_max_overflow,
        pool_recycle=settings.db_pool_recycle,
    )
    session_factory = async_sessionmaker(engine, expire_on_commit=False)
    connection = await aio_pika.connect_robust(settings.inventory_amqp_url)

    try:
        async with connection:
            channel = await connection.channel()
            queue = await declare_topology(
                channel,
                service_name="inventory",
                queue_name=QUEUE_NAME,
                routing_keys=("product.created.v2",),
            )
            await consume(
                queue, build_product_event_handler(session_factory), prefetch_count=1
            )
            logger.info("inventory-worker: product-event consumer started")

            for command_type, handler in COMMAND_HANDLERS.items():
                command_queue = await declare_command_topology(channel, command_type)
                await consume_command(command_queue, session_factory, handler)
            logger.info("inventory-worker: reservation command consumers started")

            await asyncio.gather(
                asyncio.Future(),
                reservation_sweep.run(
                    session_factory,
                    interval_seconds=settings.inventory_reservation_sweep_interval_seconds,
                ),
            )
    finally:
        await engine.dispose()


if __name__ == "__main__":
    asyncio.run(main())
