import asyncio
import json
import uuid
from collections.abc import AsyncIterator

import aio_pika
import pytest
import pytest_asyncio
from aio_pika import ExchangeType
from aio_pika.abc import AbstractChannel
from kernel_platform.consumer import consume
from kernel_platform.outbox.models import Base
from kernel_platform.outbox.settings import EVENTS_EXCHANGE_NAME
from kernel_platform.topology import declare_topology
from sqlalchemy.ext.asyncio import AsyncEngine, AsyncSession, async_sessionmaker

from api.worker import build_user_event_handler
from infrastructure.db.user_projection import UserProjectionRow

pytestmark = pytest.mark.asyncio(loop_scope="session")

SERVICE_NAME = "support-service"


@pytest_asyncio.fixture(scope="session", loop_scope="session", autouse=True)
async def support_schema(db_engine: AsyncEngine) -> AsyncIterator[None]:
    async with db_engine.begin() as connection:
        await connection.run_sync(Base.metadata.create_all)
    try:
        yield
    finally:
        async with db_engine.begin() as connection:
            await connection.run_sync(Base.metadata.drop_all)


async def _publish_user_event(
    channel: AbstractChannel,
    *,
    message_id: int,
    event_type: str,
    user_id: uuid.UUID,
    role: str | None = None,
    is_active: bool | None = None,
) -> None:
    exchange = await channel.get_exchange(EVENTS_EXCHANGE_NAME)
    await exchange.publish(
        aio_pika.Message(
            body=json.dumps(
                {
                    "user_id": str(user_id),
                    **({"role": role} if role is not None else {}),
                    **({"is_active": is_active} if is_active is not None else {}),
                }
            ).encode(),
            message_id=str(message_id),
            type=event_type,
        ),
        routing_key=event_type,
    )


async def _wait_for_projection(
    session_factory: async_sessionmaker[AsyncSession],
    user_id: uuid.UUID,
    *,
    version: int,
) -> UserProjectionRow:
    for _ in range(100):
        async with session_factory() as session:
            row = await session.get(UserProjectionRow, user_id)
        if row is not None and row.last_applied_outbox_id >= version:
            return row
        await asyncio.sleep(0.05)
    raise AssertionError(f"user_projection was not updated to version {version}")


async def test_worker_projects_user_events_idempotently_and_by_version(
    channel: AbstractChannel,
    db_engine: AsyncEngine,
) -> None:
    session_factory = async_sessionmaker(db_engine, expire_on_commit=False)
    await channel.declare_exchange(
        EVENTS_EXCHANGE_NAME, ExchangeType.TOPIC, durable=True
    )
    queue = await declare_topology(channel, service_name=SERVICE_NAME)
    await queue.purge()
    consumer_tag = await consume(queue, build_user_event_handler(session_factory))
    user_id = uuid.uuid4()

    try:
        for message_id, event_type, role, is_active in (
            (201, "user.registered.v1", None, None),
            (202, "user.activated.v1", None, None),
            (203, "user.deactivated.v1", None, None),
            (204, "user.role_changed.v1", "admin", None),
        ):
            await _publish_user_event(
                channel,
                message_id=message_id,
                event_type=event_type,
                user_id=user_id,
                role=role,
                is_active=is_active,
            )

        projection = await _wait_for_projection(session_factory, user_id, version=204)
        assert projection.role == "admin"
        assert projection.is_active is False
        assert projection.deleted is False

        # Повторная доставка последнего события и устаревшее, доставленное
        # не по порядку, — оба должны быть no-op (ADR 0012 — упорядочено,
        # идемпотентно по версии).
        await _publish_user_event(
            channel,
            message_id=204,
            event_type="user.role_changed.v1",
            user_id=user_id,
            role="user",
        )
        await _publish_user_event(
            channel, message_id=199, event_type="user.activated.v1", user_id=user_id
        )
        await asyncio.sleep(0.2)

        async with session_factory() as session:
            stored = await session.get(UserProjectionRow, user_id)
        assert stored is not None
        assert stored.role == "admin"
        assert stored.is_active is False
        assert stored.last_applied_outbox_id == 204
    finally:
        await queue.cancel(consumer_tag)


async def test_worker_tombstones_a_deleted_user_and_stale_events_cannot_revive_it(
    channel: AbstractChannel,
    db_engine: AsyncEngine,
) -> None:
    session_factory = async_sessionmaker(db_engine, expire_on_commit=False)
    await channel.declare_exchange(
        EVENTS_EXCHANGE_NAME, ExchangeType.TOPIC, durable=True
    )
    queue = await declare_topology(channel, service_name=SERVICE_NAME)
    await queue.purge()
    consumer_tag = await consume(queue, build_user_event_handler(session_factory))
    user_id = uuid.uuid4()

    try:
        await _publish_user_event(
            channel, message_id=301, event_type="user.registered.v1", user_id=user_id
        )
        await _wait_for_projection(session_factory, user_id, version=301)

        await _publish_user_event(
            channel, message_id=302, event_type="user.deleted.v1", user_id=user_id
        )
        deleted = await _wait_for_projection(session_factory, user_id, version=302)
        assert deleted.deleted is True
        assert deleted.is_active is False

        # Устаревшая, уже вытесненная активация не может воскресить tombstone.
        await _publish_user_event(
            channel, message_id=250, event_type="user.activated.v1", user_id=user_id
        )
        await asyncio.sleep(0.2)

        async with session_factory() as session:
            stored = await session.get(UserProjectionRow, user_id)
        assert stored is not None
        assert stored.deleted is True
        assert stored.is_active is False
        assert stored.last_applied_outbox_id == 302
    finally:
        await queue.cancel(consumer_tag)
