# ruff: noqa: E501
"""Outbox/inbox atomicity (issue #371, Seams for TDD #1 — mandatory before
anything else, architect brief Risk #1/D5): форсированное исключение из
`psp_client.authorize()` (monkeypatch) ПОСЛЕ inbox-claim, ДО
`session.add(OutboxMessage(...))`. Доказывает, что `PaymentCommandUnitOfWork`'s
no-op `commit()`/`__aexit__` (D5) не крашится и не оставляет частичного
состояния — `consume_command`'s собственный `async with session.begin():`
(`kernel_platform/commands.py`) откатывает ВСЁ вместе: ни `InboxMessage`, ни
`payment_authorizations`-строка, ни `OutboxMessage` не персистятся."""

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

from api.workers.commands.payment_commands import handle_authorize_command
from infrastructure.db.entity_configurations.models import PaymentAuthorizationModel
from infrastructure.psp.mock_psp_adapter import MockPspAdapter

pytestmark = pytest.mark.asyncio(loop_scope="session")


@pytest_asyncio.fixture
async def command_session_factory(
    db_engine: AsyncEngine,
) -> async_sessionmaker[AsyncSession]:
    return async_sessionmaker(db_engine, expire_on_commit=False)


def _authorize_command(*, command_id: uuid.UUID | None = None) -> Command:
    return Command(
        command_id=command_id or uuid.uuid4(),
        command_type="payment.authorize.v1",
        causation_id=uuid.uuid4(),
        correlation_id=str(uuid.uuid4()),
        payload={"amount": 1000, "payment_method_token": "success"},
    )


async def test_a_failure_after_inbox_claim_rolls_back_the_whole_command(
    channel: AbstractChannel,
    command_session_factory: async_sessionmaker[AsyncSession],
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    async def failing_authorize(
        self: MockPspAdapter, payment_method_token: str, amount: int
    ) -> object:
        raise RuntimeError(
            "forced PSP failure after inbox-claim, before the business mutation"
        )

    monkeypatch.setattr(MockPspAdapter, "authorize", failing_authorize)

    queue = await declare_command_topology(channel, "payment.authorize.v1")
    await queue.purge()
    exchange = await channel.get_exchange(COMMANDS_EXCHANGE_NAME)
    command = _authorize_command()
    failed = asyncio.Event()

    async def handler(session: AsyncSession, received: Command) -> None:
        try:
            await handle_authorize_command(session, received)
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
            payment_count = await session.scalar(
                select(func.count())
                .select_from(PaymentAuthorizationModel)
                .where(
                    PaymentAuthorizationModel.idempotency_key == str(command.command_id)
                )
            )
            outbox_count = await session.scalar(
                select(func.count())
                .select_from(OutboxMessage)
                .where(
                    OutboxMessage.payload["correlation_id"].astext
                    == command.correlation_id
                )
            )
        assert inbox_count == 0
        assert payment_count == 0
        assert outbox_count == 0
    finally:
        await queue.cancel(consumer_tag)
