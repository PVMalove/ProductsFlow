import asyncio
import json
import uuid
from collections.abc import AsyncIterator

import aio_pika
import pytest
import pytest_asyncio
from aio_pika import ExchangeType
from aio_pika.abc import AbstractChannel
from kernel_domain.result import Result
from kernel_platform.consumer import consume
from kernel_platform.outbox.models import Base, OutboxMessage
from kernel_platform.outbox.publisher import EVENTS_EXCHANGE_NAME
from kernel_platform.topology import declare_topology
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncEngine, AsyncSession, async_sessionmaker

from api.worker import build_user_event_handler
from domain.entities.ticket import Ticket
from domain.ticket_status import TicketStatus
from infrastructure.db.entity_configurations.models import (
    ProcessedMessage,
    TicketMessageModel,
    TicketModel,
)
from infrastructure.db.ticket_repository import TicketRepository

pytestmark = pytest.mark.asyncio(loop_scope="session")

SERVICE_NAME = "support-service"
USER_EVENTS_QUEUE = "support-service.user-events"


@pytest_asyncio.fixture(scope="session", loop_scope="session", autouse=True)
async def support_schema(db_engine: AsyncEngine) -> AsyncIterator[None]:
    async with db_engine.begin() as connection:
        await connection.run_sync(Base.metadata.create_all)
    try:
        yield
    finally:
        async with db_engine.begin() as connection:
            await connection.run_sync(Base.metadata.drop_all)


async def _publish_user_deleted(
    channel: AbstractChannel,
    *,
    message_id: int,
    user_id: uuid.UUID,
) -> None:
    exchange = await channel.get_exchange(EVENTS_EXCHANGE_NAME)
    await exchange.publish(
        aio_pika.Message(
            body=json.dumps({"user_id": str(user_id)}).encode(),
            message_id=str(message_id),
            type="user.deleted.v1",
        ),
        routing_key="user.deleted.v1",
    )


async def _wait_for_processed(
    session_factory: async_sessionmaker[AsyncSession], message_id: int
) -> None:
    for _ in range(100):
        async with session_factory() as session:
            processed = await session.get(ProcessedMessage, message_id)
        if processed is not None:
            return
        await asyncio.sleep(0.05)
    raise AssertionError(f"message {message_id} was not processed")


async def test_user_deletion_is_atomic_and_idempotent(
    db_engine: AsyncEngine,
) -> None:
    session_factory = async_sessionmaker(db_engine, expire_on_commit=False)
    user_id = uuid.uuid4()
    ticket = Ticket.create(
        author_id=user_id, subject="Subject", first_message="Private message"
    ).value
    async with session_factory() as session:
        await TicketRepository(session).create(ticket)
        await session.commit()

    message = type(
        "IncomingMessage",
        (),
        {
            "message_id": "9001",
            "type": "user.deleted.v1",
            "routing_key": "user.deleted.v1",
            "body": json.dumps({"user_id": str(user_id)}).encode(),
        },
    )()
    handler = build_user_event_handler(session_factory)
    await handler(message)  # type: ignore[arg-type]
    await handler(message)  # type: ignore[arg-type]

    async with session_factory() as session:
        stored_ticket = await session.get(TicketModel, ticket.id.value)
        messages = list(
            (
                await session.scalars(
                    select(TicketMessageModel)
                    .where(TicketMessageModel.ticket_id == ticket.id.value)
                    .order_by(TicketMessageModel.created_at, TicketMessageModel.id)
                )
            ).all()
        )
        outbox = list(
            (
                await session.scalars(
                    select(OutboxMessage)
                    .where(OutboxMessage.aggregate_id == ticket.id.value)
                    .order_by(OutboxMessage.id)
                )
            ).all()
        )
        processed_count = await session.scalar(
            select(func.count())
            .select_from(ProcessedMessage)
            .where(ProcessedMessage.message_id == 9001)
        )

    assert stored_ticket is not None
    assert stored_ticket.author_id is None
    assert stored_ticket.status == "CLOSED"
    assert len(messages) == 2
    assert messages[0].author_id is None
    assert messages[1].author_id is None
    assert messages[1].is_system is True
    assert messages[1].body == "[Пользователь удалён]"
    assert [event.event_type for event in outbox] == [
        "ticket.created.v1",
        "ticket.status_changed.v1",
        "ticket.message_added.v1",
    ]
    assert all("body" not in event.payload for event in outbox)
    assert processed_count == 1


async def test_rabbitmq_contract_consumes_support_queue_idempotently(
    channel: AbstractChannel,
    db_engine: AsyncEngine,
) -> None:
    await channel.declare_exchange(
        EVENTS_EXCHANGE_NAME, ExchangeType.TOPIC, durable=True
    )
    queue = await declare_topology(channel, service_name=SERVICE_NAME)
    await queue.purge()
    session_factory = async_sessionmaker(db_engine, expire_on_commit=False)
    consumer_tag = await consume(queue, build_user_event_handler(session_factory))
    user_id = uuid.uuid4()
    ticket = Ticket.create(
        author_id=user_id, subject="Subject", first_message="Private message"
    ).value
    async with session_factory() as session:
        await TicketRepository(session).create(ticket)
        await session.commit()

    try:
        await _publish_user_deleted(channel, message_id=9002, user_id=user_id)
        await _wait_for_processed(session_factory, 9002)
        await _publish_user_deleted(channel, message_id=9002, user_id=user_id)
        await asyncio.sleep(0.2)
    finally:
        await queue.cancel(consumer_tag)

    async with session_factory() as session:
        system_count = await session.scalar(
            select(func.count())
            .select_from(TicketMessageModel)
            .where(
                TicketMessageModel.ticket_id == ticket.id.value,
                TicketMessageModel.is_system.is_(True),
            )
        )

    assert system_count == 1


async def test_user_deletion_serializes_with_concurrent_ticket_message(
    db_engine: AsyncEngine,
) -> None:
    session_factory = async_sessionmaker(db_engine, expire_on_commit=False)
    user_id = uuid.uuid4()
    ticket = Ticket.create(
        author_id=user_id, subject="Subject", first_message="Private message"
    ).value
    async with session_factory() as session:
        await TicketRepository(session).create(ticket)
        await session.commit()

    deletion_message = type(
        "IncomingMessage",
        (),
        {
            "message_id": "9003",
            "type": "user.deleted.v1",
            "routing_key": "user.deleted.v1",
            "body": json.dumps({"user_id": str(user_id)}).encode(),
        },
    )()

    async def delete_user() -> None:
        await build_user_event_handler(session_factory)(  # type: ignore[arg-type]
            deletion_message
        )

    async def append_message() -> None:
        async with session_factory() as session:
            await TicketRepository(session).add_message(
                ticket_id=ticket.id,
                actor_id=user_id,
                body="Concurrent message",
                is_admin=False,
            )
            await session.commit()

    await asyncio.gather(delete_user(), append_message())

    async with session_factory() as session:
        stored_ticket = await session.get(TicketModel, ticket.id.value)
        messages = list(
            (
                await session.scalars(
                    select(TicketMessageModel).where(
                        TicketMessageModel.ticket_id == ticket.id.value
                    )
                )
            ).all()
        )

    assert stored_ticket is not None
    assert stored_ticket.author_id is None
    assert stored_ticket.status == TicketStatus.CLOSED.value
    assert sum(message.is_system for message in messages) == 1
    assert all(message.author_id is None for message in messages)


async def test_transaction_failure_rolls_back_inbox_and_retry_completes(
    db_engine: AsyncEngine,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    session_factory = async_sessionmaker(db_engine, expire_on_commit=False)
    user_id = uuid.uuid4()
    ticket = Ticket.create(
        author_id=user_id, subject="Subject", first_message="Private message"
    ).value
    async with session_factory() as session:
        await TicketRepository(session).create(ticket)
        await session.commit()

    original = Ticket.anonymize_deleted_user
    failed = False

    def fail_once(current: Ticket, deleted_user_id: uuid.UUID) -> Result[bool]:
        nonlocal failed
        if not failed:
            failed = True
            raise RuntimeError("temporary transaction failure")
        return original(current, deleted_user_id)

    monkeypatch.setattr(Ticket, "anonymize_deleted_user", fail_once)
    message = type(
        "IncomingMessage",
        (),
        {
            "message_id": "9004",
            "type": "user.deleted.v1",
            "routing_key": "user.deleted.v1",
            "body": json.dumps({"user_id": str(user_id)}).encode(),
        },
    )()
    handler = build_user_event_handler(session_factory)

    with pytest.raises(RuntimeError):
        await handler(message)  # type: ignore[arg-type]

    async with session_factory() as session:
        assert await session.get(ProcessedMessage, 9004) is None

    monkeypatch.undo()
    await handler(message)  # type: ignore[arg-type]
    await _wait_for_processed(session_factory, 9004)

    async with session_factory() as session:
        stored_ticket = await session.get(TicketModel, ticket.id.value)
        system_count = await session.scalar(
            select(func.count())
            .select_from(TicketMessageModel)
            .where(
                TicketMessageModel.ticket_id == ticket.id.value,
                TicketMessageModel.is_system.is_(True),
            )
        )

    assert stored_ticket is not None
    assert stored_ticket.author_id is None
    assert stored_ticket.status == TicketStatus.CLOSED.value
    assert system_count == 1
