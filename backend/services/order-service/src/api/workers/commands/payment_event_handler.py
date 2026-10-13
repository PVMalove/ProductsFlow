# ruff: noqa: E501
"""Message-driven адаптер фактов payment-service (issue #375, D7; issue #376,
D7) — мирует `inventory_event_handler.py`: `processed_messages`-гейт по
`(source="payment", message_id)` + делегирование бизнес-применения
`ApplyAuthorizationResultCommandHandler` (результаты `payment.authorize.v1`)
или `ApplyCaptureResultCommandHandler` (`payment.captured.v1`). Тип события
выбирает route в одной таблице `_ROUTES` (issue #376, R6). Одна очередь на
producer сохраняет порядок событий payment при `prefetch_count=1`.
`payment.capture_unknown.v1` нарочно не привязан: reconciliation — вне
issue #376 (R3 брифа). `payment.voided.v1` (issue #377, D7) привязан только
для подтверждения: факт не меняет Order, но без привязки неподтверждённая
публикация payment-service ретраится бесконечно."""

import json
import logging
import uuid
from collections.abc import Awaitable, Callable
from functools import partial
from typing import Any

from aio_pika.abc import AbstractIncomingMessage
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from api.workers.commands.inbox import (
    PAYMENT_SOURCE,
    ParsedEvent,
    claim_message,
    parse_outbox_message_id,
)
from application.commands.apply_authorization_result import (
    ApplyAuthorizationResultCommand,
    ApplyAuthorizationResultCommandHandler,
)
from application.commands.apply_capture_result import (
    ApplyCaptureResultCommand,
    ApplyCaptureResultCommandHandler,
)
from domain.entities.order import AuthorizationOutcome
from infrastructure.db.order_repository import OrderRepository
from infrastructure.db.saga_command_outbox_repository import (
    SagaCommandOutboxRepository,
)

logger = logging.getLogger(__name__)

QUEUE_NAME = "order.payment-events"
AUTHORIZATION_OUTCOME_BY_EVENT_TYPE: dict[str, AuthorizationOutcome] = {
    "payment.authorized.v1": AuthorizationOutcome.AUTHORIZED,
    "payment.authorization_declined.v1": AuthorizationOutcome.DECLINED,
    "payment.authorization_timed_out.v1": AuthorizationOutcome.TIMED_OUT,
}
CAPTURED_EVENT_TYPE = "payment.captured.v1"
VOIDED_EVENT_TYPE = "payment.voided.v1"


def _event_type(message: AbstractIncomingMessage) -> str:
    event_type = message.type or message.routing_key
    if event_type not in PAYMENT_EVENT_TYPES:
        raise ValueError(f"Unsupported payment event type: {event_type!r}")
    return event_type


def _json_object(body: bytes) -> dict[str, Any]:
    try:
        payload: object = json.loads(body)
    except (UnicodeDecodeError, json.JSONDecodeError) as exc:
        raise ValueError("Payment event payload is not valid JSON") from exc
    if not isinstance(payload, dict):
        raise ValueError("Payment event payload must be a JSON object")
    return payload


def parse_authorization_result(
    event_type: str, body: bytes
) -> ApplyAuthorizationResultCommand:
    """Парсит payload фактов авторизации payment-service
    (`{authorization_id, correlation_id, causation_id}`). `correlation_id`
    эхом возвращает `correlation_id` команды — это `str(order_id)`
    (`reservation_outbox_publisher.build_command`)."""
    try:
        outcome = AUTHORIZATION_OUTCOME_BY_EVENT_TYPE[event_type]
    except KeyError as exc:
        raise ValueError(f"Unsupported payment event type: {event_type!r}") from exc
    payload = _json_object(body)

    try:
        order_id = uuid.UUID(str(payload["correlation_id"]))
        authorization_id = uuid.UUID(str(payload["authorization_id"]))
    except (KeyError, TypeError, ValueError) as exc:
        raise ValueError(f"Invalid payment event payload: {payload!r}") from exc

    return ApplyAuthorizationResultCommand(
        order_id=order_id, authorization_id=authorization_id, outcome=outcome
    )


def parse_capture_result(body: bytes) -> ApplyCaptureResultCommand:
    """Парсит payload `payment.captured.v1` (`{authorization_id,
    correlation_id, causation_id}`, issue #376, D7): `correlation_id` —
    `str(order_id)`, `causation_id` — id команды `payment.capture.v1` этого
    Order (оба эхом из команды); `authorization_id` сверяется с авторизацией
    Order."""
    payload = _json_object(body)

    try:
        order_id = uuid.UUID(str(payload["correlation_id"]))
        authorization_id = uuid.UUID(str(payload["authorization_id"]))
        causation_id = uuid.UUID(str(payload["causation_id"]))
    except (KeyError, TypeError, ValueError) as exc:
        raise ValueError(f"Invalid payment event payload: {payload!r}") from exc

    return ApplyCaptureResultCommand(
        order_id=order_id, authorization_id=authorization_id, causation_id=causation_id
    )


def parse_voided_order_id(body: bytes) -> uuid.UUID:
    """Парсит payload `payment.voided.v1` (`{authorization_id,
    correlation_id, causation_id}`, issue #377, D7) — нужен только
    `correlation_id` (`str(order_id)`): ключ inbox-гейта (`ParsedEvent`) для
    идемпотентного подтверждения факта."""
    payload = _json_object(body)

    try:
        return uuid.UUID(str(payload["correlation_id"]))
    except (KeyError, TypeError, ValueError) as exc:
        raise ValueError(f"Invalid payment event payload: {payload!r}") from exc


def _route_authorization_result(event_type: str, body: bytes) -> ParsedEvent:
    command = parse_authorization_result(event_type, body)

    async def apply(session: AsyncSession) -> None:
        await ApplyAuthorizationResultCommandHandler(
            OrderRepository(session), SagaCommandOutboxRepository(session)
        ).execute(command)

    return ParsedEvent(command.order_id, apply)


def _route_captured(body: bytes) -> ParsedEvent:
    command = parse_capture_result(body)

    async def apply(session: AsyncSession) -> None:
        await ApplyCaptureResultCommandHandler(OrderRepository(session)).execute(
            command
        )

    return ParsedEvent(command.order_id, apply)


def _route_voided(body: bytes) -> ParsedEvent:
    order_id = parse_voided_order_id(body)

    async def apply(_session: AsyncSession) -> None:
        # issue #377, D7: Order — инициатор void; факт только подтверждается
        # inbox-гейтом. Состояние Order уже терминально, Cart не ждёт void.
        return None

    return ParsedEvent(order_id, apply)


# Единственная точка диспетчеризации фактов payment по типу события (issue
# #376, R6): новый факт — одна запись здесь, привязка очереди выводится из неё.
_ROUTES: dict[str, Callable[[bytes], ParsedEvent]] = {
    **{
        event_type: partial(_route_authorization_result, event_type)
        for event_type in AUTHORIZATION_OUTCOME_BY_EVENT_TYPE
    },
    CAPTURED_EVENT_TYPE: _route_captured,
    VOIDED_EVENT_TYPE: _route_voided,
}
# Все факты payment, которые order-worker привязывает к своей очереди.
PAYMENT_EVENT_TYPES = tuple(_ROUTES)


async def handle_payment_event(
    message: AbstractIncomingMessage,
    session_factory: async_sessionmaker[AsyncSession],
) -> None:
    event_type = _event_type(message)
    message_id = parse_outbox_message_id(message)
    event = _ROUTES[event_type](message.body)

    async with session_factory() as session:
        async with session.begin():
            if not await claim_message(
                session, source=PAYMENT_SOURCE, message_id=message_id
            ):
                logger.info(
                    "order-worker: %s message %s already processed; skipping",
                    PAYMENT_SOURCE,
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


def build_payment_event_handler(
    session_factory: async_sessionmaker[AsyncSession],
) -> Callable[[AbstractIncomingMessage], Awaitable[None]]:
    async def _handler(message: AbstractIncomingMessage) -> None:
        await handle_payment_event(message, session_factory)

    return _handler
