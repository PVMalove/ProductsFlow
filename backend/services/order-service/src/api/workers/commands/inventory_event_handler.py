# ruff: noqa: E501
"""Message-driven адаптер событий inventory (issue #372, D7/D8; issue #375,
D7) — мирует `api/worker.py`-style consumer'ов #367/#369's
`handle_product_event`: собственный `processed_messages`-гейт по
`(source, message_id)` (issue #375, D4) + делегирование бизнес-применения
`ApplyReservationResultCommandHandler` (`inventory.reserved.v1`),
`ApplyReservationReleaseCommandHandler` (`inventory.released.v1`) или
`ApplyAllocationResultCommandHandler` (`inventory.allocated.v1`, issue #376,
D7) — чистые функции, без AMQP-деталей. Тип события выбирает route в одной
таблице `_ROUTES` (issue #376, R6). Одна очередь на producer сохраняет
порядок событий inventory при `prefetch_count=1`."""

import json
import logging
import uuid
from collections.abc import Awaitable, Callable
from typing import Any

from aio_pika.abc import AbstractIncomingMessage
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from api.workers.commands.inbox import (
    INVENTORY_SOURCE,
    ParsedEvent,
    claim_message,
    parse_outbox_message_id,
)
from application.commands.apply_allocation_result import (
    ApplyAllocationResultCommand,
    ApplyAllocationResultCommandHandler,
)
from application.commands.apply_reservation_release import (
    ApplyReservationReleaseCommand,
    ApplyReservationReleaseCommandHandler,
)
from application.commands.apply_reservation_result import (
    ApplyReservationResultCommand,
    ApplyReservationResultCommandHandler,
)
from infrastructure.db.cart_repository import CartRepository
from infrastructure.db.order_repository import OrderRepository
from infrastructure.db.saga_command_outbox_repository import (
    SagaCommandOutboxRepository,
)

logger = logging.getLogger(__name__)

RESERVED_EVENT_TYPE = "inventory.reserved.v1"
RELEASED_EVENT_TYPE = "inventory.released.v1"
ALLOCATED_EVENT_TYPE = "inventory.allocated.v1"
QUEUE_NAME = "order.inventory-events"


def _event_type(message: AbstractIncomingMessage) -> str:
    event_type = message.type or message.routing_key
    if event_type not in INVENTORY_EVENT_TYPES:
        raise ValueError(f"Unsupported reservation event type: {event_type!r}")
    return event_type


def _json_object(body: bytes) -> dict[str, Any]:
    try:
        payload: object = json.loads(body)
    except (UnicodeDecodeError, json.JSONDecodeError) as exc:
        raise ValueError("Reservation event payload is not valid JSON") from exc
    if not isinstance(payload, dict):
        raise ValueError("Reservation event payload must be a JSON object")
    return payload


def parse_reservation_result(body: bytes) -> ApplyReservationResultCommand:
    """Парсит `InventoryReserved.to_payload()` (inventory-service, issue
    #370, находка 7) — только `order_id`/`confirmed_lines[].product_id`
    нужны для применения результата."""
    payload = _json_object(body)

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


def parse_reservation_release(body: bytes) -> ApplyReservationReleaseCommand:
    """Парсит payload `inventory.released.v1` (`{order_id, reason,
    released_lines}`) — для компенсации нужен только `order_id`: любой
    `reason` (`manual`/`expired`) означает, что резерв освобождён."""
    payload = _json_object(body)

    try:
        order_id = uuid.UUID(str(payload["order_id"]))
    except (KeyError, ValueError) as exc:
        raise ValueError(f"Invalid reservation event payload: {payload!r}") from exc

    return ApplyReservationReleaseCommand(order_id=order_id)


def parse_allocation_result(body: bytes) -> ApplyAllocationResultCommand:
    """Парсит payload `inventory.allocated.v1` (`{order_id,
    allocated_lines}`, issue #376, D7) — для перехода к capture нужен только
    `order_id`."""
    payload = _json_object(body)

    try:
        order_id = uuid.UUID(str(payload["order_id"]))
    except (KeyError, ValueError) as exc:
        raise ValueError(f"Invalid reservation event payload: {payload!r}") from exc

    return ApplyAllocationResultCommand(order_id=order_id)


def _route_reserved(body: bytes, payment_method_token: str) -> ParsedEvent:
    command = parse_reservation_result(body)

    async def apply(session: AsyncSession) -> None:
        await ApplyReservationResultCommandHandler(
            OrderRepository(session),
            CartRepository(session),
            SagaCommandOutboxRepository(session),
            payment_method_token=payment_method_token,
        ).execute(command)

    return ParsedEvent(command.order_id, apply)


def _route_released(body: bytes, _payment_method_token: str) -> ParsedEvent:
    command = parse_reservation_release(body)

    async def apply(session: AsyncSession) -> None:
        await ApplyReservationReleaseCommandHandler(
            OrderRepository(session), CartRepository(session)
        ).execute(command)

    return ParsedEvent(command.order_id, apply)


def _route_allocated(body: bytes, _payment_method_token: str) -> ParsedEvent:
    command = parse_allocation_result(body)

    async def apply(session: AsyncSession) -> None:
        await ApplyAllocationResultCommandHandler(
            OrderRepository(session), SagaCommandOutboxRepository(session)
        ).execute(command)

    return ParsedEvent(command.order_id, apply)


# Единственная точка диспетчеризации фактов inventory по типу события (issue
# #376, R6): новый факт — одна запись здесь, привязка очереди выводится из неё.
_ROUTES: dict[str, Callable[[bytes, str], ParsedEvent]] = {
    RESERVED_EVENT_TYPE: _route_reserved,
    RELEASED_EVENT_TYPE: _route_released,
    ALLOCATED_EVENT_TYPE: _route_allocated,
}
INVENTORY_EVENT_TYPES = tuple(_ROUTES)


async def handle_inventory_event(
    message: AbstractIncomingMessage,
    session_factory: async_sessionmaker[AsyncSession],
    *,
    payment_method_token: str,
) -> None:
    event_type = _event_type(message)
    message_id = parse_outbox_message_id(message)
    event = _ROUTES[event_type](message.body, payment_method_token)

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

            await event.apply(session)

    logger.info(
        "order-worker: applied %s for order_id=%s at outbox message %s",
        event_type,
        event.order_id,
        message_id,
    )


def build_inventory_event_handler(
    session_factory: async_sessionmaker[AsyncSession],
    payment_method_token: str,
) -> Callable[[AbstractIncomingMessage], Awaitable[None]]:
    async def _handler(message: AbstractIncomingMessage) -> None:
        await handle_inventory_event(
            message, session_factory, payment_method_token=payment_method_token
        )

    return _handler
