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
from infrastructure.db.unit_of_work import SqlSupportUnitOfWork
from infrastructure.db.user_projection import upsert_user_projection

logger = logging.getLogger(__name__)

USER_DELETED_EVENT = "user.deleted.v1"
SUPPORTED_USER_EVENT_TYPES = frozenset(
    {
        "user.registered.v1",
        "user.activated.v1",
        "user.deactivated.v1",
        "user.role_changed.v1",
        USER_DELETED_EVENT,
    }
)


@dataclass(frozen=True)
class UserEventSnapshot:
    user_id: uuid.UUID
    role: str | None
    is_active: bool | None
    deleted: bool | None


@dataclass(frozen=True)
class DeletedUserEvent:
    user_id: uuid.UUID


def _event_type(message: AbstractIncomingMessage) -> str:
    event_type = message.type or message.routing_key
    if event_type not in SUPPORTED_USER_EVENT_TYPES:
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


def _user_id_from_payload(payload: dict[str, object]) -> uuid.UUID:
    raw_user_id = payload.get("user_id", payload.get("id"))
    try:
        return uuid.UUID(str(raw_user_id))
    except (AttributeError, ValueError) as exc:
        raise ValueError(f"Invalid user id: {raw_user_id!r}") from exc


def _parse_deleted_user_event(message: AbstractIncomingMessage) -> DeletedUserEvent:
    payload = _decode_payload(message.body)
    return DeletedUserEvent(_user_id_from_payload(payload))


def _decode_payload(body: bytes) -> dict[str, object]:
    try:
        payload: object = json.loads(body)
    except (UnicodeDecodeError, json.JSONDecodeError) as exc:
        raise ValueError("User event payload is not valid JSON") from exc
    if not isinstance(payload, dict):
        raise ValueError("User event payload must be a JSON object")
    return payload


def _parse_user_event_snapshot(event_type: str, body: bytes) -> UserEventSnapshot:
    payload = _decode_payload(body)
    user_id = _user_id_from_payload(payload)

    role = payload.get("role", payload.get("new_role"))
    if role is not None and (not isinstance(role, str) or not role):
        raise ValueError("User event role must be a non-empty string")

    is_active = payload.get("is_active")
    if is_active is not None and not isinstance(is_active, bool):
        raise ValueError("User event is_active must be boolean")

    deleted: bool | None = None
    if event_type == "user.registered.v1":
        role = "user" if role is None else role
        is_active = True if is_active is None else is_active
        deleted = False
    elif event_type == "user.activated.v1":
        is_active = True
    elif event_type == "user.deactivated.v1":
        is_active = False
    elif event_type == "user.role_changed.v1" and role is None:
        raise ValueError("Role-changed event must contain role")
    elif event_type == USER_DELETED_EVENT:
        is_active = False
        deleted = True

    return UserEventSnapshot(user_id, role, is_active, deleted)


async def _apply_projection(
    session_factory: async_sessionmaker[AsyncSession],
    *,
    event_type: str,
    message_id: int,
    body: bytes,
) -> UserEventSnapshot:
    """Идемпотентный, упорядоченный upsert проекции (ADR 0012) — безопасен к
    повторам сам по себе через `last_applied_outbox_id`, независимо от
    message-id inbox, который защищает анонимизацию тикетов ниже."""
    snapshot = _parse_user_event_snapshot(event_type, body)
    async with session_factory() as session:
        await upsert_user_projection(
            session,
            user_id=snapshot.user_id,
            role=snapshot.role,
            is_active=snapshot.is_active,
            deleted=snapshot.deleted,
            last_applied_outbox_id=message_id,
            commit=True,
        )
    return snapshot


async def handle_user_event(
    message: AbstractIncomingMessage,
    session_factory: async_sessionmaker[AsyncSession],
) -> None:
    """Применяет одно событие пользователя identity к локальной проекции и,
    для удаления, дополнительно анонимизирует тикеты вызывающего через уже
    существующий message-id inbox (ADR 0012)."""
    event_type = _event_type(message)
    message_id = _message_id(message)

    snapshot = await _apply_projection(
        session_factory, event_type=event_type, message_id=message_id, body=message.body
    )
    logger.info(
        "support-worker: applied %s for user %s at outbox version %s",
        event_type,
        snapshot.user_id,
        message_id,
    )

    if event_type != USER_DELETED_EVENT:
        return

    async with session_factory() as session:
        processed = await ProcessUserDeletionCommandHandler(
            SqlSupportUnitOfWork(session)
        ).execute(
            ProcessUserDeletionCommand(message_id=message_id, user_id=snapshot.user_id)
        )
    logger.info(
        "support-worker: %s ticket anonymization for user %s (message %s)",
        "applied" if processed else "skipped duplicate",
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
    """Запускает консьюмер проекции user-событий и удаления Support."""
    if not settings.support_database_url:
        raise RuntimeError("SUPPORT_DATABASE_URL must be configured")
    engine = create_async_engine(
        settings.support_database_url,
        pool_pre_ping=True,
        pool_size=settings.db_pool_size,
        max_overflow=settings.db_max_overflow,
        pool_recycle=settings.db_pool_recycle,
    )
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
