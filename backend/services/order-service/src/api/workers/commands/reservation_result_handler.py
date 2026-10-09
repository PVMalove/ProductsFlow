# ruff: noqa: E501
"""Message-driven адаптер `inventory.reserved.v1` (issue #372, D7/D8) —
мирует `api/worker.py`-style consumer'ов #367/#369's `handle_product_event`:
собственный `processed_messages`-гейт по `(source, message_id)` (issue #375,
D4) + делегирование бизнес-применения `ApplyReservationResultCommandHandler`
(чистая функция, без AMQP-деталей)."""

import json
import logging
import uuid
from collections.abc import Awaitable, Callable

from aio_pika.abc import AbstractIncomingMessage
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from api.workers.commands.inbox import (
    INVENTORY_SOURCE,
    claim_message,
    parse_outbox_message_id,
)
from application.commands.apply_reservation_result import (
    ApplyReservationResultCommand,
    ApplyReservationResultCommandHandler,
)
from infrastructure.db.cart_repository import CartRepository
from infrastructure.db.order_repository import OrderRepository
from infrastructure.db.reservation_outbox_repository import (
    ReservationOutboxRepository,
)

logger = logging.getLogger(__name__)

RESERVED_EVENT_TYPE = "inventory.reserved.v1"
QUEUE_NAME = "order.inventory-events"


def _event_type(message: AbstractIncomingMessage) -> str:
    event_type = message.type or message.routing_key
    if event_type != RESERVED_EVENT_TYPE:
        raise ValueError(f"Unsupported reservation event type: {event_type!r}")
    return event_type


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
    *,
    payment_method_token: str,
) -> None:
    event_type = _event_type(message)
    message_id = parse_outbox_message_id(message)
    command = parse_reservation_result(message.body)

    async with session_factory() as session:
        async with session.begin():
            if not await claim_message(
                session, source=INVENTORY_SOURCE, message_id=message_id
            ):
                logger.info(
                    "order-worker: %s message %s already processed; skipping",
                    INVENTORY_SOURCE,
                    message_id,
                )
                return

            handler = ApplyReservationResultCommandHandler(
                OrderRepository(session),
                CartRepository(session),
                ReservationOutboxRepository(session),
                payment_method_token=payment_method_token,
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
    payment_method_token: str,
) -> Callable[[AbstractIncomingMessage], Awaitable[None]]:
    async def _handler(message: AbstractIncomingMessage) -> None:
        await handle_reservation_result(
            message, session_factory, payment_method_token=payment_method_token
        )

    return _handler
