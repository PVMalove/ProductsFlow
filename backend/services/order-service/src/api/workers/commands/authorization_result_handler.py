# ruff: noqa: E501
"""Message-driven адаптер результатов `payment.authorize.v1` (issue #375,
D7) — мирует `reservation_result_handler.py`: `processed_messages`-гейт по
`(source="payment", message_id)` + делегирование бизнес-применения
`ApplyAuthorizationResultCommandHandler`."""

import json
import logging
import uuid
from collections.abc import Awaitable, Callable

from aio_pika.abc import AbstractIncomingMessage
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from api.workers.commands.inbox import (
    PAYMENT_SOURCE,
    claim_message,
    parse_outbox_message_id,
)
from application.commands.apply_authorization_result import (
    ApplyAuthorizationResultCommand,
    ApplyAuthorizationResultCommandHandler,
)
from domain.entities.order import AuthorizationOutcome
from infrastructure.db.order_repository import OrderRepository
from infrastructure.db.reservation_outbox_repository import (
    ReservationOutboxRepository,
)

logger = logging.getLogger(__name__)

QUEUE_NAME = "order.payment-events"
AUTHORIZATION_OUTCOME_BY_EVENT_TYPE: dict[str, AuthorizationOutcome] = {
    "payment.authorized.v1": AuthorizationOutcome.AUTHORIZED,
    "payment.authorization_declined.v1": AuthorizationOutcome.DECLINED,
    "payment.authorization_timed_out.v1": AuthorizationOutcome.TIMED_OUT,
}


def _event_type(message: AbstractIncomingMessage) -> str:
    event_type = message.type or message.routing_key
    if event_type not in AUTHORIZATION_OUTCOME_BY_EVENT_TYPE:
        raise ValueError(f"Unsupported payment event type: {event_type!r}")
    return event_type


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
    try:
        payload: object = json.loads(body)
    except (UnicodeDecodeError, json.JSONDecodeError) as exc:
        raise ValueError("Payment event payload is not valid JSON") from exc
    if not isinstance(payload, dict):
        raise ValueError("Payment event payload must be a JSON object")

    try:
        order_id = uuid.UUID(str(payload["correlation_id"]))
        authorization_id = uuid.UUID(str(payload["authorization_id"]))
    except (KeyError, TypeError, ValueError) as exc:
        raise ValueError(f"Invalid payment event payload: {payload!r}") from exc

    return ApplyAuthorizationResultCommand(
        order_id=order_id, authorization_id=authorization_id, outcome=outcome
    )


async def handle_authorization_result(
    message: AbstractIncomingMessage,
    session_factory: async_sessionmaker[AsyncSession],
) -> None:
    event_type = _event_type(message)
    message_id = parse_outbox_message_id(message)
    command = parse_authorization_result(event_type, message.body)

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

            handler = ApplyAuthorizationResultCommandHandler(
                OrderRepository(session), ReservationOutboxRepository(session)
            )
            await handler.execute(command)

    logger.info(
        "order-worker: applied %s for order_id=%s at outbox message %s",
        event_type,
        command.order_id,
        message_id,
    )


def build_authorization_result_handler(
    session_factory: async_sessionmaker[AsyncSession],
) -> Callable[[AbstractIncomingMessage], Awaitable[None]]:
    async def _handler(message: AbstractIncomingMessage) -> None:
        await handle_authorization_result(message, session_factory)

    return _handler
