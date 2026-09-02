import asyncio
import json
import logging
import uuid
from collections.abc import Awaitable, Callable
from dataclasses import dataclass

import aio_pika
from aio_pika.abc import AbstractIncomingMessage
from kernel_platform.consumer import consume
from kernel_platform.topology import declare_topology
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine

from application.commands import (
    ProcessUserDeletionCommand,
    ProcessUserDeletionCommandHandler,
)
from core.settings import settings
from infrastructure.db.ticket_repository import TicketRepository

logger = logging.getLogger(__name__)

USER_DELETED_EVENT = "user.deleted.v1"
USER_EVENTS_QUEUE = "support-service.user-events"
IGNORED_USER_EVENTS = frozenset(
    {
        "user.registered.v1",
        "user.activated.v1",
        "user.deactivated.v1",
        "user.role_changed.v1",
    }
)


@dataclass(frozen=True)
class DeletedUserEvent:
    user_id: uuid.UUID


def _message_id(message: AbstractIncomingMessage) -> int:
    raw_message_id = message.message_id
    try:
        message_id = int(raw_message_id) if raw_message_id is not None else 0
    except (TypeError, ValueError) as exc:
        raise ValueError(f"Invalid outbox message id: {raw_message_id!r}") from exc
    if message_id <= 0:
        raise ValueError(f"Invalid outbox message id: {raw_message_id!r}")
    return message_id


def _parse_deleted_user_event(message: AbstractIncomingMessage) -> DeletedUserEvent:
    event_type = message.type or message.routing_key
    # The shared retry ladder republishes through the default exchange and
    # preserves the body but not the AMQP type, so a retry returns with the
    # service queue as its routing key. This queue only handles deletion
    # events, therefore that routing key remains an unambiguous signal here.
    if event_type not in {USER_DELETED_EVENT, USER_EVENTS_QUEUE}:
        raise ValueError(f"Unsupported user event type: {event_type!r}")
    try:
        payload: object = json.loads(message.body)
    except (UnicodeDecodeError, json.JSONDecodeError) as exc:
        raise ValueError("User deletion payload is not valid JSON") from exc
    if not isinstance(payload, dict):
        raise ValueError("User deletion payload must be a JSON object")

    raw_user_id = payload.get("user_id", payload.get("id"))
    try:
        user_id = uuid.UUID(str(raw_user_id))
    except (AttributeError, ValueError) as exc:
        raise ValueError(f"Invalid user id: {raw_user_id!r}") from exc
    return DeletedUserEvent(user_id)


async def handle_user_event(
    message: AbstractIncomingMessage,
    session_factory: async_sessionmaker[AsyncSession],
) -> None:
    """Process one identity deletion delivery through the local inbox."""
    event_type = message.type or message.routing_key
    if event_type in IGNORED_USER_EVENTS:
        logger.info("support-worker: ignoring %s", event_type)
        return
    message_id = _message_id(message)
    event = _parse_deleted_user_event(message)
    async with session_factory() as session:
        processed = await ProcessUserDeletionCommandHandler(
            TicketRepository(session)
        ).execute(
            ProcessUserDeletionCommand(message_id=message_id, user_id=event.user_id)
        )
    logger.info(
        "support-worker: %s user %s (message %s)",
        "applied" if processed else "skipped duplicate",
        event.user_id,
        message_id,
    )


def build_user_event_handler(
    session_factory: async_sessionmaker[AsyncSession],
) -> Callable[[AbstractIncomingMessage], Awaitable[None]]:
    async def _handler(message: AbstractIncomingMessage) -> None:
        await handle_user_event(message, session_factory)

    return _handler


async def main() -> None:
    """Run Support's user-deletion consumer."""
    if not settings.support_database_url:
        raise RuntimeError("SUPPORT_DATABASE_URL must be configured")
    engine = create_async_engine(settings.support_database_url)
    session_factory = async_sessionmaker(engine, expire_on_commit=False)
    connection = await aio_pika.connect_robust(settings.support_amqp_url)

    try:
        async with connection:
            channel = await connection.channel()
            queue = await declare_topology(channel, service_name="support-service")
            await consume(queue, build_user_event_handler(session_factory))
            logger.info("support-worker: user-event consumer started")
            await asyncio.Future()
    finally:
        await engine.dispose()


if __name__ == "__main__":
    asyncio.run(main())
