# ruff: noqa: E501
"""End-to-end reserve/release через реальные `consume_command`/`publish_command`
(issue #370, Seams for TDD #9, по образцу kernel-platform's
`test_commands.py`). Покрывает: (a) inbox-слой идемпотентность — повтор
ОДНОГО `command_id`; (b) business-result-слой идемпотентность — ДВА разных
`command_id`, тот же `order_id` (D3/находка 6); (c) release после reserve
восстанавливает `reserved` и публикует `inventory.released.v1`(reason=manual)
в outbox, повторный release — no-op."""

import asyncio
import uuid

import pytest
import pytest_asyncio
from aio_pika.abc import AbstractChannel
from kernel_platform.commands import Command, consume_command, publish_command
from kernel_platform.outbox.models import InboxMessage, OutboxMessage
from kernel_platform.topology import COMMANDS_EXCHANGE_NAME, declare_command_topology
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncEngine, AsyncSession, async_sessionmaker

from api.reservation_commands import handle_release_command, handle_reserve_command
from infrastructure.db.entity_configurations.models import (
    InventoryModel,
    ReservationModel,
)

pytestmark = pytest.mark.asyncio(loop_scope="session")


@pytest_asyncio.fixture
async def command_session_factory(
    db_engine: AsyncEngine,
) -> async_sessionmaker[AsyncSession]:
    return async_sessionmaker(db_engine, expire_on_commit=False)


async def _seed_inventory(
    session_factory: async_sessionmaker[AsyncSession],
    product_id: uuid.UUID,
    quantity: int,
) -> None:
    async with session_factory() as session:
        session.add(
            InventoryModel(product_id=product_id, quantity=quantity, reserved=0)
        )
        await session.commit()


def _reserve_command(
    order_id: uuid.UUID,
    lines: list[tuple[uuid.UUID, int]],
    *,
    command_id: uuid.UUID | None = None,
) -> Command:
    return Command(
        command_id=command_id or uuid.uuid4(),
        command_type="inventory.reserve.v1",
        causation_id=uuid.uuid4(),
        correlation_id=str(order_id),
        payload={
            "order_id": str(order_id),
            "lines": [
                {"product_id": str(product_id), "quantity": quantity}
                for product_id, quantity in lines
            ],
        },
    )


async def _wait_for_reservation_row(
    session_factory: async_sessionmaker[AsyncSession], order_id: uuid.UUID
) -> None:
    """Дожидается фактического COMMIT'а транзакции reserve-хендлера — `handled`
    (`asyncio.Event`) внутри обёртки-хендлера срабатывает ДО того, как
    `consume_command`'s `async with session.begin():` завершит commit
    (обёртка выполняется ВНУТРИ этого блока), поэтому свежая сессия из
    ДРУГОГО соединения (release-консьюмер) может ещё не видеть строку."""
    for _ in range(100):
        async with session_factory() as session:
            row = await session.get(ReservationModel, order_id)
        if row is not None:
            return
        await asyncio.sleep(0.05)
    raise AssertionError("reservation row was not committed within the timeout")


async def _wait_for_reserved_quantity(
    session_factory: async_sessionmaker[AsyncSession],
    product_id: uuid.UUID,
    expected: int,
) -> int:
    """Same commit-visibility race as `_wait_for_reservation_row`, on the
    release side: `released_event` fires inside the handler, before
    `consume_command`'s surrounding transaction actually commits."""
    reserved = None
    for _ in range(100):
        async with session_factory() as session:
            reserved = await session.scalar(
                select(InventoryModel.reserved).where(
                    InventoryModel.product_id == product_id
                )
            )
        if reserved == expected:
            return reserved
        await asyncio.sleep(0.05)
    assert reserved is not None
    return reserved


def _release_command(order_id: uuid.UUID) -> Command:
    return Command(
        command_id=uuid.uuid4(),
        command_type="inventory.release.v1",
        causation_id=uuid.uuid4(),
        correlation_id=str(order_id),
        payload={"order_id": str(order_id)},
    )


async def test_duplicate_command_id_redelivery_does_not_double_reserve(
    channel: AbstractChannel,
    command_session_factory: async_sessionmaker[AsyncSession],
) -> None:
    queue = await declare_command_topology(channel, "inventory.reserve.v1")
    await queue.purge()
    exchange = await channel.get_exchange(COMMANDS_EXCHANGE_NAME)
    product_id = uuid.uuid4()
    order_id = uuid.uuid4()
    await _seed_inventory(command_session_factory, product_id, 10)
    command = _reserve_command(order_id, [(product_id, 4)])
    handled = asyncio.Event()

    async def handler(session: AsyncSession, received: Command) -> None:
        await handle_reserve_command(session, received)
        handled.set()

    consumer_tag = await consume_command(queue, command_session_factory, handler)
    try:
        await publish_command(exchange, command, timeout_seconds=5.0)
        await asyncio.wait_for(handled.wait(), timeout=5)

        # Redeliver the exact same command_id — the inbox gate must ACK it
        # without re-invoking the handler at all.
        await publish_command(exchange, command, timeout_seconds=5.0)
        await asyncio.sleep(0.3)

        async with command_session_factory() as session:
            reserved = await session.scalar(
                select(InventoryModel.reserved).where(
                    InventoryModel.product_id == product_id
                )
            )
            inbox_count = await session.scalar(
                select(func.count())
                .select_from(InboxMessage)
                .where(InboxMessage.command_id == command.command_id)
            )
        assert reserved == 4
        assert inbox_count == 1
    finally:
        await queue.cancel(consumer_tag)


async def test_different_command_id_same_order_id_does_not_double_reserve(
    channel: AbstractChannel,
    command_session_factory: async_sessionmaker[AsyncSession],
) -> None:
    queue = await declare_command_topology(channel, "inventory.reserve.v1")
    await queue.purge()
    exchange = await channel.get_exchange(COMMANDS_EXCHANGE_NAME)
    product_id = uuid.uuid4()
    order_id = uuid.uuid4()
    await _seed_inventory(command_session_factory, product_id, 10)
    handled = asyncio.Event()

    async def handler(session: AsyncSession, received: Command) -> None:
        await handle_reserve_command(session, received)
        handled.set()

    consumer_tag = await consume_command(queue, command_session_factory, handler)
    try:
        await publish_command(
            exchange, _reserve_command(order_id, [(product_id, 4)]), timeout_seconds=5.0
        )
        await asyncio.wait_for(handled.wait(), timeout=5)
        handled.clear()

        # A DIFFERENT command_id for the same order_id — passes the inbox
        # gate (new command_id) but must be a business-layer no-op (D3).
        await publish_command(
            exchange, _reserve_command(order_id, [(product_id, 4)]), timeout_seconds=5.0
        )
        await asyncio.wait_for(handled.wait(), timeout=5)

        async with command_session_factory() as session:
            reserved = await session.scalar(
                select(InventoryModel.reserved).where(
                    InventoryModel.product_id == product_id
                )
            )
            reservation_count = await session.scalar(
                select(func.count())
                .select_from(ReservationModel)
                .where(ReservationModel.order_id == order_id)
            )
        assert reserved == 4
        assert reservation_count == 1
    finally:
        await queue.cancel(consumer_tag)


async def test_release_after_reserve_restores_reserved_and_is_idempotent(
    channel: AbstractChannel,
    command_session_factory: async_sessionmaker[AsyncSession],
) -> None:
    reserve_queue = await declare_command_topology(channel, "inventory.reserve.v1")
    release_queue = await declare_command_topology(channel, "inventory.release.v1")
    await reserve_queue.purge()
    await release_queue.purge()
    exchange = await channel.get_exchange(COMMANDS_EXCHANGE_NAME)
    product_id = uuid.uuid4()
    order_id = uuid.uuid4()
    await _seed_inventory(command_session_factory, product_id, 10)
    reserved_event = asyncio.Event()
    released_event = asyncio.Event()

    async def reserve_handler(session: AsyncSession, received: Command) -> None:
        await handle_reserve_command(session, received)
        reserved_event.set()

    async def release_handler(session: AsyncSession, received: Command) -> None:
        await handle_release_command(session, received)
        released_event.set()

    reserve_tag = await consume_command(
        reserve_queue, command_session_factory, reserve_handler
    )
    release_tag = await consume_command(
        release_queue, command_session_factory, release_handler
    )
    try:
        await publish_command(
            exchange, _reserve_command(order_id, [(product_id, 4)]), timeout_seconds=5.0
        )
        await asyncio.wait_for(reserved_event.wait(), timeout=5)
        # reserve.v1 and release.v1 are two INDEPENDENT queues/consumers — no
        # cross-queue ordering guarantee like the single-queue prefetch=1
        # serialization the other two tests rely on. Wait for the reserve
        # transaction to actually commit before publishing release, or the
        # release consumer's own session may not yet see the reservation row.
        await _wait_for_reservation_row(command_session_factory, order_id)

        await publish_command(exchange, _release_command(order_id), timeout_seconds=5.0)
        await asyncio.wait_for(released_event.wait(), timeout=5)
        # Same commit-visibility race as above, on the release side —
        # `released_event.set()` fires inside the handler, before the
        # surrounding transaction commits.
        reserved = await _wait_for_reserved_quantity(
            command_session_factory, product_id, 0
        )

        async with command_session_factory() as session:
            released_outbox_count = await session.scalar(
                select(func.count())
                .select_from(OutboxMessage)
                .where(
                    OutboxMessage.event_type == "inventory.released.v1",
                    OutboxMessage.aggregate_id == order_id,
                )
            )
        assert reserved == 0
        assert released_outbox_count == 1

        # A second, independent release command for the same order_id —
        # the reservation is already RELEASED, so this must be a no-op:
        # neither `reserved` nor the outbox row count changes. No new commit
        # to wait for here (a no-op mutates nothing), a short buffer is
        # enough to let the handler actually run before asserting.
        released_event.clear()
        await publish_command(exchange, _release_command(order_id), timeout_seconds=5.0)
        await asyncio.wait_for(released_event.wait(), timeout=5)
        await asyncio.sleep(0.3)

        async with command_session_factory() as session:
            reserved_after = await session.scalar(
                select(InventoryModel.reserved).where(
                    InventoryModel.product_id == product_id
                )
            )
            released_outbox_count_after = await session.scalar(
                select(func.count())
                .select_from(OutboxMessage)
                .where(
                    OutboxMessage.event_type == "inventory.released.v1",
                    OutboxMessage.aggregate_id == order_id,
                )
            )
        assert reserved_after == 0
        assert released_outbox_count_after == 1
    finally:
        await reserve_queue.cancel(reserve_tag)
        await release_queue.cancel(release_tag)
