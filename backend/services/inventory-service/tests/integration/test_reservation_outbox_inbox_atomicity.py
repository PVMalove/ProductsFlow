# ruff: noqa: E501
"""Outbox/inbox atomicity (issue #370, Seams for TDD #11, DoD explicit) —
форсированное исключение ПОСЛЕ inbox-claim и ПОСЛЕ реальной
`Inventory.reserve()`-мутации (уже применённой к сессии), но ДО завершения
бизнес-мутации `Reservation` (`try_create`, monkeypatch репозитория).
Доказывает, что `consume_command`'s `async with session.begin():`
(`kernel_platform/commands.py`, находка 2 архитектурного брифа) откатывает
ВСЁ вместе: ни `InboxMessage`, ни `Inventory.reserved`, ни `Reservation`,
ни строка `OutboxMessage` не персистятся."""

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

from api.reservation_commands import handle_reserve_command
from infrastructure.db.entity_configurations.models import (
    InventoryModel,
    ReservationModel,
)
from infrastructure.db.reservation_repository import ReservationRepository

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
    order_id: uuid.UUID, product_id: uuid.UUID, quantity: int
) -> Command:
    return Command(
        command_id=uuid.uuid4(),
        command_type="inventory.reserve.v1",
        causation_id=uuid.uuid4(),
        correlation_id=str(order_id),
        payload={
            "order_id": str(order_id),
            "lines": [{"product_id": str(product_id), "quantity": quantity}],
        },
    )


async def test_a_failure_after_inventory_mutation_rolls_back_the_whole_command(
    channel: AbstractChannel,
    command_session_factory: async_sessionmaker[AsyncSession],
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    async def failing_try_create(
        self: ReservationRepository, reservation: object
    ) -> bool:
        raise RuntimeError(
            "forced failure after Inventory.reserve() already mutated the session"
        )

    monkeypatch.setattr(ReservationRepository, "try_create", failing_try_create)

    queue = await declare_command_topology(channel, "inventory.reserve.v1")
    await queue.purge()
    exchange = await channel.get_exchange(COMMANDS_EXCHANGE_NAME)
    product_id = uuid.uuid4()
    order_id = uuid.uuid4()
    await _seed_inventory(command_session_factory, product_id, 10)
    command = _reserve_command(order_id, product_id, 4)
    failed = asyncio.Event()

    async def handler(session: AsyncSession, received: Command) -> None:
        try:
            await handle_reserve_command(session, received)
        finally:
            failed.set()

    consumer_tag = await consume_command(queue, command_session_factory, handler)
    try:
        await publish_command(exchange, command, timeout_seconds=5.0)
        await asyncio.wait_for(failed.wait(), timeout=5)
        # Default retry.5s stage is 5000ms — checking well within that window
        # guarantees the redelivered retry hasn't landed yet.
        await asyncio.sleep(0.3)

        async with command_session_factory() as session:
            inbox_count = await session.scalar(
                select(func.count())
                .select_from(InboxMessage)
                .where(InboxMessage.command_id == command.command_id)
            )
            reservation_count = await session.scalar(
                select(func.count())
                .select_from(ReservationModel)
                .where(ReservationModel.order_id == order_id)
            )
            reserved = await session.scalar(
                select(InventoryModel.reserved).where(
                    InventoryModel.product_id == product_id
                )
            )
            outbox_count = await session.scalar(
                select(func.count())
                .select_from(OutboxMessage)
                .where(OutboxMessage.aggregate_id == order_id)
            )
        assert inbox_count == 0
        assert reservation_count == 0
        assert reserved == 0
        assert outbox_count == 0
    finally:
        await queue.cancel(consumer_tag)
