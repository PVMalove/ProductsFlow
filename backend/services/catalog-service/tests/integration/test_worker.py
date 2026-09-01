import asyncio
import json
import uuid

import aio_pika
import pytest
import pytest_asyncio
from aio_pika import ExchangeType
from aio_pika.abc import AbstractChannel
from kernel_platform.consumer import consume
from kernel_platform.outbox.publisher import EVENTS_EXCHANGE_NAME
from kernel_platform.topology import declare_topology
from sqlalchemy import func, select, text
from sqlalchemy.ext.asyncio import AsyncEngine, AsyncSession, async_sessionmaker

from infrastructure.db.owner_read_model import OwnerReadModelRow
from infrastructure.db.processed_messages import ProcessedMessage
from presentation.worker import build_user_event_handler

pytestmark = pytest.mark.asyncio(loop_scope="session")

SERVICE_NAME = "catalog"
USER_EVENTS_QUEUE = "catalog.user-events"


@pytest_asyncio.fixture(loop_scope="session")
async def worker_session_factory(
    db_engine: AsyncEngine,
) -> async_sessionmaker[AsyncSession]:
    async with db_engine.begin() as connection:
        await connection.execute(text("TRUNCATE processed_messages, owner_read_model"))
    return async_sessionmaker(db_engine, expire_on_commit=False)


async def _publish_user_event(
    channel: AbstractChannel,
    *,
    message_id: int,
    event_type: str,
    user_id: uuid.UUID,
    role: str,
    is_active: bool,
) -> None:
    exchange = await channel.get_exchange(EVENTS_EXCHANGE_NAME)
    await exchange.publish(
        aio_pika.Message(
            body=json.dumps(
                {"user_id": str(user_id), "role": role, "is_active": is_active}
            ).encode(),
            message_id=str(message_id),
            type=event_type,
        ),
        routing_key=event_type,
    )


async def _wait_for_owner(
    session_factory: async_sessionmaker[AsyncSession],
    user_id: uuid.UUID,
    *,
    version: int,
) -> OwnerReadModelRow:
    async def _find() -> OwnerReadModelRow | None:
        async with session_factory() as session:
            return await session.get(OwnerReadModelRow, user_id)

    for _ in range(100):
        row = await _find()
        if row is not None and row.last_applied_outbox_id >= version:
            return row
        await asyncio.sleep(0.05)
    raise AssertionError(f"owner_read_model was not updated to version {version}")


async def test_worker_syncs_user_events_idempotently_and_by_version(
    channel: AbstractChannel,
    worker_session_factory: async_sessionmaker[AsyncSession],
) -> None:
    await channel.declare_exchange(
        EVENTS_EXCHANGE_NAME, ExchangeType.TOPIC, durable=True
    )
    queue = await declare_topology(channel, service_name=SERVICE_NAME)
    await queue.purge()
    handler = build_user_event_handler(worker_session_factory)
    consumer_tag = await consume(queue, handler)
    user_id = uuid.uuid4()

    try:
        for message_id, event_type, role, is_active in (
            (101, "user.registered.v1", "user", True),
            (102, "user.activated.v1", "user", True),
            (103, "user.deactivated.v1", "user", False),
            (104, "user.role_changed.v1", "admin", True),
        ):
            await _publish_user_event(
                channel,
                message_id=message_id,
                event_type=event_type,
                user_id=user_id,
                role=role,
                is_active=is_active,
            )

        owner = await _wait_for_owner(worker_session_factory, user_id, version=104)
        assert owner.role == "admin"
        assert owner.is_active is True
        assert owner.last_applied_outbox_id == 104

        await _publish_user_event(
            channel,
            message_id=104,
            event_type="user.role_changed.v1",
            user_id=user_id,
            role="user",
            is_active=False,
        )
        await _publish_user_event(
            channel,
            message_id=99,
            event_type="user.activated.v1",
            user_id=user_id,
            role="user",
            is_active=True,
        )
        await asyncio.sleep(0.2)

        async with worker_session_factory() as session:
            stored_owner = await session.get(OwnerReadModelRow, user_id)
            processed_count = await session.scalar(
                select(func.count())
                .select_from(ProcessedMessage)
                .where(ProcessedMessage.message_id.in_([99, 101, 102, 103, 104]))
            )

        assert stored_owner is not None
        assert stored_owner.role == "admin"
        assert stored_owner.is_active is True
        assert stored_owner.last_applied_outbox_id == 104
        assert processed_count == 5
    finally:
        await queue.cancel(consumer_tag)
