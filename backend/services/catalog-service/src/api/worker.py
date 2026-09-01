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
from sqlalchemy.dialects.postgresql import insert
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine

from core.settings import settings
from infrastructure.db.owner_read_model import upsert_owner_read_model
from infrastructure.db.processed_messages import ProcessedMessage

logger = logging.getLogger(__name__)

USER_EVENT_TYPES = frozenset(
    {
        "user.registered.v1",
        "user.activated.v1",
        "user.deactivated.v1",
        "user.role_changed.v1",
    }
)


@dataclass(frozen=True)
class UserEventSnapshot:
    user_id: uuid.UUID
    role: str | None
    is_active: bool | None


def _event_type(message: AbstractIncomingMessage) -> str:
    event_type = message.type or message.routing_key
    if event_type not in USER_EVENT_TYPES:
        raise ValueError(f"Unsupported user event type: {event_type!r}")
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


def _parse_user_event_snapshot(event_type: str, body: bytes) -> UserEventSnapshot:
    try:
        payload: object = json.loads(body)
    except (UnicodeDecodeError, json.JSONDecodeError) as exc:
        raise ValueError("User event payload is not valid JSON") from exc
    if not isinstance(payload, dict):
        raise ValueError("User event payload must be a JSON object")

    raw_user_id = payload.get("user_id", payload.get("id"))
    try:
        user_id = uuid.UUID(str(raw_user_id))
    except (AttributeError, ValueError) as exc:
        raise ValueError(f"Invalid user id: {raw_user_id!r}") from exc

    role = payload.get("role", payload.get("new_role"))
    if role is not None and (not isinstance(role, str) or not role):
        raise ValueError("User event role must be a non-empty string")

    is_active = payload.get("is_active")
    if is_active is not None and not isinstance(is_active, bool):
        raise ValueError("User event is_active must be boolean")

    if event_type == "user.registered.v1":
        role = "user" if role is None else role
        is_active = True if is_active is None else is_active
    elif event_type == "user.activated.v1":
        is_active = True
    elif event_type == "user.deactivated.v1":
        is_active = False
    elif event_type == "user.role_changed.v1" and role is None:
        raise ValueError("Role-changed event must contain role")

    return UserEventSnapshot(user_id, role, is_active)


async def handle_user_event(
    message: AbstractIncomingMessage,
    session_factory: async_sessionmaker[AsyncSession],
) -> None:
    """Apply one user snapshot and record its message id atomically."""
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
                    "catalog-worker: message %s already processed; skipping",
                    message_id,
                )
                return

            snapshot = _parse_user_event_snapshot(event_type, message.body)
            await upsert_owner_read_model(
                session,
                user_id=snapshot.user_id,
                role=snapshot.role,
                is_active=snapshot.is_active,
                last_applied_outbox_id=message_id,
                commit=False,
            )

    logger.info(
        "catalog-worker: applied %s for user %s at outbox version %s",
        event_type,
        snapshot.user_id,
        message_id,
    )


def build_user_event_handler(
    session_factory: async_sessionmaker[AsyncSession],
) -> Callable[[AbstractIncomingMessage], Awaitable[None]]:
    async def _handler(message: AbstractIncomingMessage) -> None:
        await handle_user_event(message, session_factory)

    return _handler


async def main() -> None:
    """Run catalog's user-event projection worker (ADR 0010/0019)."""
    engine = create_async_engine(settings.catalog_database_url)
    session_factory = async_sessionmaker(engine, expire_on_commit=False)
    connection = await aio_pika.connect_robust(settings.catalog_amqp_url)

    try:
        async with connection:
            channel = await connection.channel()
            queue = await declare_topology(channel, service_name="catalog")
            await consume(queue, build_user_event_handler(session_factory))
            logger.info("catalog-worker: user-event consumer started")
            await asyncio.Future()
    finally:
        await engine.dispose()


if __name__ == "__main__":
    asyncio.run(main())
