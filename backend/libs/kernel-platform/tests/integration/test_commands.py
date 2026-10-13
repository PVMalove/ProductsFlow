import asyncio
import uuid
from collections.abc import AsyncIterator
from datetime import UTC, datetime

import pytest
import pytest_asyncio
from aio_pika.abc import AbstractChannel
from opentelemetry import trace
from opentelemetry.sdk.trace import TracerProvider
from opentelemetry.sdk.trace.export import SimpleSpanProcessor
from opentelemetry.sdk.trace.export.in_memory_span_exporter import (
    InMemorySpanExporter,
)
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncEngine, AsyncSession, async_sessionmaker

from kernel_platform.commands import Command, consume_command, publish_command
from kernel_platform.outbox.models import Base, InboxMessage, OutboxMessage
from kernel_platform.topology import COMMANDS_EXCHANGE_NAME, declare_command_topology

pytestmark = pytest.mark.asyncio(loop_scope="session")


@pytest_asyncio.fixture(scope="session", loop_scope="session", autouse=True)
async def command_schema(db_engine: AsyncEngine) -> AsyncIterator[None]:
    async with db_engine.begin() as connection:
        await connection.run_sync(Base.metadata.create_all)
    try:
        yield
    finally:
        async with db_engine.begin() as connection:
            await connection.run_sync(Base.metadata.drop_all)


@pytest.fixture
def command_session_factory(
    db_engine: AsyncEngine,
) -> async_sessionmaker[AsyncSession]:
    return async_sessionmaker(db_engine, expire_on_commit=False)


async def test_duplicate_command_is_acked_without_repeating_its_business_effect(
    channel: AbstractChannel,
    command_session_factory: async_sessionmaker[AsyncSession],
) -> None:
    queue = await declare_command_topology(channel, "inventory.reserve.v1")
    commands_exchange = await channel.get_exchange(COMMANDS_EXCHANGE_NAME)
    command = Command(
        command_id=uuid.uuid4(),
        command_type="inventory.reserve.v1",
        causation_id=uuid.uuid4(),
        correlation_id="checkout-42",
        payload={"order_id": "order-42"},
    )
    handled = asyncio.Event()
    handled_ids: list[uuid.UUID] = []

    async def handler(session: AsyncSession, received: Command) -> None:
        handled_ids.append(received.command_id)
        session.add(
            OutboxMessage(
                id=1,
                aggregate_type="Reservation",
                aggregate_id=uuid.uuid4(),
                event_type="inventory.reserved.v1",
                payload={"order_id": "order-42"},
                occurred_at=datetime.now(UTC),
                trace_context=None,
            )
        )
        handled.set()

    consumer_tag = await consume_command(queue, command_session_factory, handler)
    try:
        await publish_command(commands_exchange, command, timeout_seconds=5.0)
        await asyncio.wait_for(handled.wait(), timeout=5)
        await publish_command(commands_exchange, command, timeout_seconds=5.0)

        for _ in range(20):
            async with command_session_factory() as session:
                inbox_count = await session.scalar(
                    select(func.count()).select_from(InboxMessage)
                )
            if inbox_count == 1:
                break
            await asyncio.sleep(0.05)

        assert handled_ids == [command.command_id]
        async with command_session_factory() as session:
            assert (
                await session.scalar(select(func.count()).select_from(InboxMessage))
                == 1
            )
            assert (
                await session.scalar(select(func.count()).select_from(OutboxMessage))
                == 1
            )
    finally:
        await queue.cancel(consumer_tag)


async def test_command_consumer_continues_the_publisher_w3c_trace(
    channel: AbstractChannel,
    command_session_factory: async_sessionmaker[AsyncSession],
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    provider = TracerProvider()
    exporter = InMemorySpanExporter()
    provider.add_span_processor(SimpleSpanProcessor(exporter))
    monkeypatch.setattr(trace, "get_tracer_provider", lambda: provider)
    queue = await declare_command_topology(channel, "payment.authorize.v1")
    commands_exchange = await channel.get_exchange(COMMANDS_EXCHANGE_NAME)
    handled = asyncio.Event()

    async def handler(_session: AsyncSession, _command: Command) -> None:
        handled.set()

    consumer_tag = await consume_command(queue, command_session_factory, handler)
    try:
        with provider.get_tracer("test").start_as_current_span("checkout"):
            await publish_command(
                commands_exchange,
                Command(
                    command_id=uuid.uuid4(),
                    command_type="payment.authorize.v1",
                    causation_id=uuid.uuid4(),
                    correlation_id="checkout-43",
                    payload={"order_id": "order-43"},
                ),
                timeout_seconds=5.0,
            )
        await asyncio.wait_for(handled.wait(), timeout=5)
    finally:
        await queue.cancel(consumer_tag)

    spans = exporter.get_finished_spans()
    checkout_span = next(span for span in spans if span.name == "checkout")
    publish_span = next(span for span in spans if span.name == "publish_command")
    consume_span = next(span for span in spans if span.name == "consume_message")

    assert publish_span.parent is not None
    assert publish_span.parent.span_id == checkout_span.context.span_id
    assert consume_span.parent is not None
    assert consume_span.parent.span_id == publish_span.context.span_id
    assert consume_span.context.trace_id == checkout_span.context.trace_id


async def test_command_retry_preserves_the_command_envelope(
    channel: AbstractChannel,
    command_session_factory: async_sessionmaker[AsyncSession],
) -> None:
    command_type = "inventory.release.v1"
    queue = await declare_command_topology(
        channel,
        command_type,
        retry_stage_ttl_ms={"retry.5s": 100, "retry.30s": 100, "retry.2m": 100},
    )
    commands_exchange = await channel.get_exchange(COMMANDS_EXCHANGE_NAME)
    command = Command(
        command_id=uuid.uuid4(),
        command_type=command_type,
        causation_id=uuid.uuid4(),
        correlation_id="checkout-44",
        payload={"order_id": "order-44"},
    )
    attempts: list[uuid.UUID] = []
    retried_successfully = asyncio.Event()

    async def handler(_session: AsyncSession, received: Command) -> None:
        attempts.append(received.command_id)
        if len(attempts) == 1:
            raise RuntimeError("transient failure")
        retried_successfully.set()

    consumer_tag = await consume_command(queue, command_session_factory, handler)
    try:
        await publish_command(commands_exchange, command, timeout_seconds=5.0)
        await asyncio.wait_for(retried_successfully.wait(), timeout=5)
    finally:
        await queue.cancel(consumer_tag)

    assert attempts == [command.command_id, command.command_id]
