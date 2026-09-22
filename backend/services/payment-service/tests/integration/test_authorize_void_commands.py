# ruff: noqa: E501
"""End-to-end authorize/void через реальные `consume_command`/`publish_command`
(issue #371, Seams for TDD #6, DoD п.9 буквально — по образцу
`kernel-platform`'s `test_commands.py` и inventory's
`test_reserve_release_commands.py`). Покрывает: (a) успешный
authorize/decline/timeout; (b) inbox-слой идемпотентность — повтор ОДНОГО
`command_id` (broker redelivery) для authorize (DoD п.3, PSP вызывается
ровно один раз); (c) void успешно авторизованного платежа и его безопасный
повторный void другим `command_id` (D7 — тихий no-op, без второй
outbox-строки, без PSP-вызова — void вообще не вызывает PSP, находка 8)."""

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

import api.workers.commands.payment_commands as payment_commands
from api.workers.commands.payment_commands import (
    handle_authorize_command,
    handle_void_command,
)
from infrastructure.db.entity_configurations.models import PaymentAuthorizationModel
from infrastructure.psp.mock_psp_adapter import MockPspAdapter

pytestmark = pytest.mark.asyncio(loop_scope="session")


class _SpyPspAdapter(MockPspAdapter):
    """Same counting idiom as tests/integration/conftest.py::SpyPspAdapter
    (issue #368), redefined here because it swaps in via a monkeypatched
    `build_psp_client`, not FastAPI's dependency override."""

    def __init__(self) -> None:
        self.authorize_calls: list[tuple[str, int]] = []

    async def authorize(self, payment_method_token: str, amount: int) -> object:  # type: ignore[override]
        self.authorize_calls.append((payment_method_token, amount))
        return await super().authorize(payment_method_token, amount)


@pytest_asyncio.fixture
async def command_session_factory(
    db_engine: AsyncEngine,
) -> async_sessionmaker[AsyncSession]:
    return async_sessionmaker(db_engine, expire_on_commit=False)


@pytest.fixture
def spy_psp(monkeypatch: pytest.MonkeyPatch) -> _SpyPspAdapter:
    psp = _SpyPspAdapter()
    monkeypatch.setattr(payment_commands, "build_psp_client", lambda settings: psp)
    return psp


def _authorize_command(
    *,
    command_id: uuid.UUID | None = None,
    payment_method_token: str = "success",
    amount: int = 1000,
) -> Command:
    return Command(
        command_id=command_id or uuid.uuid4(),
        command_type="payment.authorize.v1",
        causation_id=uuid.uuid4(),
        correlation_id=str(uuid.uuid4()),
        payload={"amount": amount, "payment_method_token": payment_method_token},
    )


def _void_command(
    authorization_id: uuid.UUID, *, command_id: uuid.UUID | None = None
) -> Command:
    return Command(
        command_id=command_id or uuid.uuid4(),
        command_type="payment.void.v1",
        causation_id=uuid.uuid4(),
        correlation_id=str(uuid.uuid4()),
        payload={"authorization_id": str(authorization_id)},
    )


async def _outbox_row_count(
    session_factory: async_sessionmaker[AsyncSession],
    event_type: str,
    authorization_id: uuid.UUID,
) -> int:
    async with session_factory() as session:
        count = await session.scalar(
            select(func.count())
            .select_from(OutboxMessage)
            .where(
                OutboxMessage.event_type == event_type,
                OutboxMessage.aggregate_id == authorization_id,
            )
        )
    assert count is not None
    return count


async def _wait_for_authorization_id(
    session_factory: async_sessionmaker[AsyncSession], idempotency_key: str
) -> uuid.UUID:
    """Cross-queue commit-visibility race (mirrors inventory's
    `_wait_for_reservation_row`): the authorize handler's own `asyncio.Event`
    fires INSIDE `consume_command`'s `session.begin()`, before that
    transaction actually commits — a fresh session on the void queue's own
    connection may not see the row yet."""
    for _ in range(100):
        async with session_factory() as session:
            authorization_id = await session.scalar(
                select(PaymentAuthorizationModel.id).where(
                    PaymentAuthorizationModel.idempotency_key == idempotency_key
                )
            )
        if authorization_id is not None:
            return authorization_id
        await asyncio.sleep(0.05)
    raise AssertionError("authorization row was not committed within the timeout")


async def _wait_for_status(
    session_factory: async_sessionmaker[AsyncSession],
    authorization_id: uuid.UUID,
    expected: str,
) -> str | None:
    status = None
    for _ in range(100):
        async with session_factory() as session:
            status = await session.scalar(
                select(PaymentAuthorizationModel.status).where(
                    PaymentAuthorizationModel.id == authorization_id
                )
            )
        if status == expected:
            return status
        await asyncio.sleep(0.05)
    return status


@pytest.mark.parametrize(
    ("token", "event_type"),
    [
        ("success", "payment.authorized.v1"),
        ("decline", "payment.authorization_declined.v1"),
        ("timeout", "payment.authorization_timed_out.v1"),
    ],
)
async def test_authorize_outcomes_produce_the_matching_outbox_event(
    channel: AbstractChannel,
    command_session_factory: async_sessionmaker[AsyncSession],
    spy_psp: _SpyPspAdapter,
    token: str,
    event_type: str,
) -> None:
    queue = await declare_command_topology(channel, "payment.authorize.v1")
    await queue.purge()
    exchange = await channel.get_exchange(COMMANDS_EXCHANGE_NAME)
    command = _authorize_command(payment_method_token=token)
    handled = asyncio.Event()

    async def handler(session: AsyncSession, received: Command) -> None:
        await handle_authorize_command(session, received)
        handled.set()

    consumer_tag = await consume_command(queue, command_session_factory, handler)
    try:
        await publish_command(exchange, command, timeout_seconds=5.0)
        await asyncio.wait_for(handled.wait(), timeout=5)

        authorization_id = await _wait_for_authorization_id(
            command_session_factory, str(command.command_id)
        )
        async with command_session_factory() as session:
            authorization_count = await session.scalar(
                select(func.count())
                .select_from(PaymentAuthorizationModel)
                .where(
                    PaymentAuthorizationModel.idempotency_key == str(command.command_id)
                )
            )
        assert authorization_count == 1
        outbox_count = await _outbox_row_count(
            command_session_factory, event_type, authorization_id
        )
        assert outbox_count == 1
    finally:
        await queue.cancel(consumer_tag)


async def test_duplicate_authorize_command_id_redelivery_calls_the_psp_once(
    channel: AbstractChannel,
    command_session_factory: async_sessionmaker[AsyncSession],
    spy_psp: _SpyPspAdapter,
) -> None:
    queue = await declare_command_topology(channel, "payment.authorize.v1")
    await queue.purge()
    exchange = await channel.get_exchange(COMMANDS_EXCHANGE_NAME)
    command = _authorize_command()
    handled = asyncio.Event()

    async def handler(session: AsyncSession, received: Command) -> None:
        await handle_authorize_command(session, received)
        handled.set()

    consumer_tag = await consume_command(queue, command_session_factory, handler)
    try:
        await publish_command(exchange, command, timeout_seconds=5.0)
        await asyncio.wait_for(handled.wait(), timeout=5)

        # Redeliver the exact same command_id — the inbox gate must ACK it
        # without re-invoking the handler at all (DoD п.3).
        await publish_command(exchange, command, timeout_seconds=5.0)
        await asyncio.sleep(0.3)

        async with command_session_factory() as session:
            inbox_count = await session.scalar(
                select(func.count())
                .select_from(InboxMessage)
                .where(InboxMessage.command_id == command.command_id)
            )
            authorization_count = await session.scalar(
                select(func.count())
                .select_from(PaymentAuthorizationModel)
                .where(
                    PaymentAuthorizationModel.idempotency_key == str(command.command_id)
                )
            )
        assert inbox_count == 1
        assert authorization_count == 1
        assert len(spy_psp.authorize_calls) == 1
    finally:
        await queue.cancel(consumer_tag)


async def test_void_of_an_authorized_payment_then_duplicate_and_repeat_void(
    channel: AbstractChannel,
    command_session_factory: async_sessionmaker[AsyncSession],
    spy_psp: _SpyPspAdapter,
) -> None:
    authorize_queue = await declare_command_topology(channel, "payment.authorize.v1")
    void_queue = await declare_command_topology(channel, "payment.void.v1")
    await authorize_queue.purge()
    await void_queue.purge()
    exchange = await channel.get_exchange(COMMANDS_EXCHANGE_NAME)
    authorized_event = asyncio.Event()
    voided_event = asyncio.Event()

    async def authorize_handler(session: AsyncSession, received: Command) -> None:
        await handle_authorize_command(session, received)
        authorized_event.set()

    async def void_handler(session: AsyncSession, received: Command) -> None:
        await handle_void_command(session, received)
        voided_event.set()

    authorize_tag = await consume_command(
        authorize_queue, command_session_factory, authorize_handler
    )
    void_tag = await consume_command(void_queue, command_session_factory, void_handler)
    try:
        authorize_command = _authorize_command()
        await publish_command(exchange, authorize_command, timeout_seconds=5.0)
        await asyncio.wait_for(authorized_event.wait(), timeout=5)

        authorization_id = await _wait_for_authorization_id(
            command_session_factory, str(authorize_command.command_id)
        )

        await publish_command(
            exchange, _void_command(authorization_id), timeout_seconds=5.0
        )
        await asyncio.wait_for(voided_event.wait(), timeout=5)

        status = await _wait_for_status(
            command_session_factory, authorization_id, "voided"
        )
        assert status == "voided"
        voided_outbox_count = await _outbox_row_count(
            command_session_factory, "payment.voided.v1", authorization_id
        )
        assert voided_outbox_count == 1

        # A second, independent void command for the same authorization_id —
        # already VOIDED, so this must be a silent no-op (D7): no exception,
        # no second outbox row, no PSP call (void never calls the PSP at
        # all — finding 8, checked below via authorize_calls staying at 1).
        voided_event.clear()
        await publish_command(
            exchange, _void_command(authorization_id), timeout_seconds=5.0
        )
        await asyncio.wait_for(voided_event.wait(), timeout=5)
        await asyncio.sleep(0.3)

        voided_outbox_count_after = await _outbox_row_count(
            command_session_factory, "payment.voided.v1", authorization_id
        )
        assert voided_outbox_count_after == 1
        assert spy_psp.authorize_calls == [("success", 1000)]
    finally:
        await authorize_queue.cancel(authorize_tag)
        await void_queue.cancel(void_tag)


async def test_duplicate_void_command_id_redelivery_is_deduplicated_by_the_inbox(
    channel: AbstractChannel,
    command_session_factory: async_sessionmaker[AsyncSession],
    spy_psp: _SpyPspAdapter,
) -> None:
    """Mirrors `test_duplicate_authorize_command_id_redelivery_calls_the_psp_once`
    but for the void queue: redelivering the exact same void `Command` object
    (same `command_id`) must be caught by the inbox-layer gate itself, not
    merely by the domain-level `void_idempotency_key` guard already exercised
    above with a *different* `command_id`."""
    authorize_queue = await declare_command_topology(channel, "payment.authorize.v1")
    void_queue = await declare_command_topology(channel, "payment.void.v1")
    await authorize_queue.purge()
    await void_queue.purge()
    exchange = await channel.get_exchange(COMMANDS_EXCHANGE_NAME)
    authorized_event = asyncio.Event()
    voided_event = asyncio.Event()

    async def authorize_handler(session: AsyncSession, received: Command) -> None:
        await handle_authorize_command(session, received)
        authorized_event.set()

    async def void_handler(session: AsyncSession, received: Command) -> None:
        await handle_void_command(session, received)
        voided_event.set()

    authorize_tag = await consume_command(
        authorize_queue, command_session_factory, authorize_handler
    )
    void_tag = await consume_command(void_queue, command_session_factory, void_handler)
    try:
        authorize_command = _authorize_command()
        await publish_command(exchange, authorize_command, timeout_seconds=5.0)
        await asyncio.wait_for(authorized_event.wait(), timeout=5)

        authorization_id = await _wait_for_authorization_id(
            command_session_factory, str(authorize_command.command_id)
        )

        void_command = _void_command(authorization_id)
        await publish_command(exchange, void_command, timeout_seconds=5.0)
        await asyncio.wait_for(voided_event.wait(), timeout=5)

        status = await _wait_for_status(
            command_session_factory, authorization_id, "voided"
        )
        assert status == "voided"

        # Redeliver the exact same command_id — the inbox gate must ACK it
        # without re-invoking the handler at all (DoD п.3), just like the
        # authorize case above.
        await publish_command(exchange, void_command, timeout_seconds=5.0)
        await asyncio.sleep(0.3)

        async with command_session_factory() as session:
            inbox_count = await session.scalar(
                select(func.count())
                .select_from(InboxMessage)
                .where(InboxMessage.command_id == void_command.command_id)
            )
        assert inbox_count == 1
        voided_outbox_count = await _outbox_row_count(
            command_session_factory, "payment.voided.v1", authorization_id
        )
        assert voided_outbox_count == 1
        async with command_session_factory() as session:
            final_status = await session.scalar(
                select(PaymentAuthorizationModel.status).where(
                    PaymentAuthorizationModel.id == authorization_id
                )
            )
        assert final_status == "voided"
    finally:
        await authorize_queue.cancel(authorize_tag)
        await void_queue.cancel(void_tag)
