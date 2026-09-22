# ruff: noqa: E501
"""Message-driven адаптер `inventory.reserved.v1` (issue #372, D7/D8) —
мирует `api/worker.py`-style consumer'ов #367/#369's `handle_product_event`:
собственный `processed_messages`-гейт по `message_id` + делегирование
бизнес-применения `ApplyReservationResultCommandHandler` (чистая функция,
без AMQP-деталей)."""

import json
import logging
import uuid
from collections.abc import Awaitable, Callable

from aio_pika.abc import AbstractIncomingMessage
from sqlalchemy.dialects.postgresql import insert
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from application.commands.apply_reservation_result import (
    ApplyReservationResultCommand,
    ApplyReservationResultCommandHandler,
)
from infrastructure.db.cart_repository import CartRepository
from infrastructure.db.entity_configurations.models import ProcessedMessageModel
from infrastructure.db.order_repository import OrderRepository

logger = logging.getLogger(__name__)

RESERVED_EVENT_TYPE = "inventory.reserved.v1"
QUEUE_NAME = "order.inventory-events"


def _event_type(message: AbstractIncomingMessage) -> str:
    event_type = message.type or message.routing_key
    if event_type != RESERVED_EVENT_TYPE:
        raise ValueError(f"Unsupported reservation event type: {event_type!r}")
    return event_type


def _message_id(message: AbstractIncomingMessage) -> int:
    # `inventory.reserved.v1` едет через generic `kernel_platform` outbox
    # (inventory-service — уже существующий producer, issue #370) — тот же
    # BigInt `message_id`, что inventory-worker's `ProcessedMessage`-гейт
    # (issue #367, находка 3) ожидает от чужого доменного события.
    raw_message_id = message.message_id
    try:
        message_id = int(raw_message_id) if raw_message_id is not None else 0
    except (TypeError, ValueError) as exc:
        raise ValueError(f"Invalid outbox message id: {raw_message_id!r}") from exc
    if message_id <= 0:
        raise ValueError(f"Invalid outbox message id: {raw_message_id!r}")
    return message_id


def parse_reservation_result(body: bytes) -> ApplyReservationResultCommand:
    """Парсит `InventoryReserved.to_payload()` (inventory-service, issue
    #370, находка 7) — только `order_id`/`confirmed_lines[].product_id`
    нужны для применения результата."""
    try:
        payload: object = json.loads(body)
    except (UnicodeDecodeError, json.JSONDecodeError) as exc:
        raise ValueError("Reservation event payload is not valid JSON") from exc
    if not isinstance(payload, dict):
        raise ValueError("Reservation event payload must be a JSON object")

    try:
        order_id = uuid.UUID(str(payload["order_id"]))
        confirmed_product_ids = frozenset(
            uuid.UUID(str(line["product_id"])) for line in payload["confirmed_lines"]
        )
    except (KeyError, TypeError, ValueError) as exc:
        raise ValueError(f"Invalid reservation event payload: {payload!r}") from exc

    return ApplyReservationResultCommand(
        order_id=order_id, confirmed_product_ids=confirmed_product_ids
    )


async def handle_reservation_result(
    message: AbstractIncomingMessage,
    session_factory: async_sessionmaker[AsyncSession],
) -> None:
    event_type = _event_type(message)
    message_id = _message_id(message)
    command = parse_reservation_result(message.body)

    async with session_factory() as session:
        async with session.begin():
            claimed_message_id = await session.scalar(
                insert(ProcessedMessageModel)
                .values(message_id=message_id)
                .on_conflict_do_nothing()
                .returning(ProcessedMessageModel.message_id)
            )
            if claimed_message_id is None:
                logger.info(
                    "order-worker: message %s already processed; skipping",
                    message_id,
                )
                return

            handler = ApplyReservationResultCommandHandler(
                OrderRepository(session), CartRepository(session)
            )
            await handler.execute(command)

    logger.info(
        "order-worker: applied %s for order_id=%s at outbox message %s",
        event_type,
        command.order_id,
        message_id,
    )


def build_reservation_result_handler(
    session_factory: async_sessionmaker[AsyncSession],
) -> Callable[[AbstractIncomingMessage], Awaitable[None]]:
    async def _handler(message: AbstractIncomingMessage) -> None:
        await handle_reservation_result(message, session_factory)

    return _handler
