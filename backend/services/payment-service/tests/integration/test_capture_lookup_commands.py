# ruff: noqa: E501
"""End-to-end capture/lookup through the real `consume_command`/
`publish_command` (issue #374, architect brief TDD seam 7, modelled on
`test_authorize_void_commands.py`). Covers: (a) a successful
`payment.capture.v1`; (b) an unknown capture (`payment.capture_unknown.v1`)
reconciled by `payment.lookup_capture.v1` into `payment.captured.v1`;
(c) a confirmed absence (`payment.capture_not_found.v1`) after which a capture
with a new key reaches the PSP again; (d) inbox-level idempotency — a
redelivery of the same capture `command_id` calls the PSP once.

The authorization row is seeded through the repository instead of a
`payment.authorize.v1` round trip — authorize over RabbitMQ is already proven
by `test_authorize_void_commands.py`, and seeding avoids its cross-queue
commit-visibility race."""

import asyncio
import uuid
from collections.abc import Awaitable, Callable

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
    handle_capture_command,
    handle_lookup_capture_command,
)
from domain.entities.payment_authorization import PaymentAuthorization
from domain.psp_client import (
    PspAuthorizeOutcome,
    PspCaptureLookupOutcome,
    PspCaptureOutcome,
)
from infrastructure.db.entity_configurations.models import PaymentAuthorizationModel
from infrastructure.db.payment_repository import PaymentAuthorizationRepository
from infrastructure.psp.mock_psp_adapter import MockPspAdapter

pytestmark = pytest.mark.asyncio(loop_scope="session")


class _SpyPspAdapter(MockPspAdapter):
    """Counts capture/lookup calls; `lookup_outcome` overrides the mock's
    lookup table, because the Test PSP itself never confirms an absence
    (brief R1) — the absence path is reachable only through a fake PSP."""

    def __init__(self) -> None:
        self.capture_calls: list[tuple[str, str]] = []
        self.lookup_capture_calls: list[tuple[str, str]] = []
        self.lookup_outcome: PspCaptureLookupOutcome | None = None

    async def capture(
        self, payment_method_token: str, idempotency_key: str
    ) -> PspCaptureOutcome:
        self.capture_calls.append((payment_method_token, idempotency_key))
        return await super().capture(payment_method_token, idempotency_key)

    async def lookup_capture(
        self, payment_method_token: str, idempotency_key: str
    ) -> PspCaptureLookupOutcome:
        self.lookup_capture_calls.append((payment_method_token, idempotency_key))
        if self.lookup_outcome is not None:
            return self.lookup_outcome
        return await super().lookup_capture(payment_method_token, idempotency_key)


_Handler = Callable[[AsyncSession, Command], Awaitable[None]]


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


async def _seed_authorization(
    session_factory: async_sessionmaker[AsyncSession], payment_method_token: str
) -> uuid.UUID:
    payment = PaymentAuthorization.create(
        str(uuid.uuid4()), 1000, payment_method_token, PspAuthorizeOutcome.SUCCESS
    ).value
    async with session_factory() as session, session.begin():
        assert await PaymentAuthorizationRepository(session).add(payment)
    return payment.id


def _capture_command(
    authorization_id: uuid.UUID, *, command_id: uuid.UUID | None = None
) -> Command:
    return Command(
        command_id=command_id or uuid.uuid4(),
        command_type="payment.capture.v1",
        causation_id=uuid.uuid4(),
        correlation_id=str(uuid.uuid4()),
        payload={"authorization_id": str(authorization_id)},
    )


def _lookup_capture_command(idempotency_key: str) -> Command:
    return Command(
        command_id=uuid.uuid4(),
        command_type="payment.lookup_capture.v1",
        causation_id=uuid.uuid4(),
        correlation_id=str(uuid.uuid4()),
        payload={"idempotency_key": idempotency_key},
    )


def _signalling(handler: _Handler, handled: asyncio.Event) -> _Handler:
    async def wrapped(session: AsyncSession, received: Command) -> None:
        await handler(session, received)
        handled.set()

    return wrapped


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


async def _wait_for_row(
    session_factory: async_sessionmaker[AsyncSession],
    authorization_id: uuid.UUID,
    *,
    status: str,
    capture_idempotency_key: str,
) -> None:
    """The handler's `asyncio.Event` fires INSIDE `consume_command`'s
    `session.begin()`, before that transaction commits — poll until the
    committed row is visible (same idiom as `test_authorize_void_commands.py`)."""
    row: tuple[str, str | None] | None = None
    for _ in range(100):
        async with session_factory() as session:
            result = await session.execute(
                select(
                    PaymentAuthorizationModel.status,
                    PaymentAuthorizationModel.capture_idempotency_key,
                ).where(PaymentAuthorizationModel.id == authorization_id)
            )
            fetched = result.one_or_none()
        row = (fetched[0], fetched[1]) if fetched is not None else None
        if row == (status, capture_idempotency_key):
            return
        await asyncio.sleep(0.05)
    raise AssertionError(
        f"expected ({status!r}, {capture_idempotency_key!r}), last seen {row!r}"
    )


async def test_capture_of_an_authorized_payment_emits_captured(
    channel: AbstractChannel,
    command_session_factory: async_sessionmaker[AsyncSession],
    spy_psp: _SpyPspAdapter,
) -> None:
    queue = await declare_command_topology(channel, "payment.capture.v1")
    await queue.purge()
    exchange = await channel.get_exchange(COMMANDS_EXCHANGE_NAME)
    authorization_id = await _seed_authorization(command_session_factory, "success")
    command = _capture_command(authorization_id)
    handled = asyncio.Event()

    consumer_tag = await consume_command(
        queue, command_session_factory, _signalling(handle_capture_command, handled)
    )
    try:
        await publish_command(exchange, command, timeout_seconds=5.0)
        await asyncio.wait_for(handled.wait(), timeout=5)

        await _wait_for_row(
            command_session_factory,
            authorization_id,
            status="captured",
            capture_idempotency_key=str(command.command_id),
        )
        assert (
            await _outbox_row_count(
                command_session_factory, "payment.captured.v1", authorization_id
            )
            == 1
        )
        assert spy_psp.capture_calls == [("success", str(command.command_id))]
    finally:
        await queue.cancel(consumer_tag)


async def test_unknown_capture_is_reconciled_by_lookup_into_captured(
    channel: AbstractChannel,
    command_session_factory: async_sessionmaker[AsyncSession],
    spy_psp: _SpyPspAdapter,
) -> None:
    capture_queue = await declare_command_topology(channel, "payment.capture.v1")
    lookup_queue = await declare_command_topology(channel, "payment.lookup_capture.v1")
    await capture_queue.purge()
    await lookup_queue.purge()
    exchange = await channel.get_exchange(COMMANDS_EXCHANGE_NAME)
    authorization_id = await _seed_authorization(
        command_session_factory, "unknown_capture"
    )
    captured_event = asyncio.Event()
    looked_up_event = asyncio.Event()

    capture_tag = await consume_command(
        capture_queue,
        command_session_factory,
        _signalling(handle_capture_command, captured_event),
    )
    lookup_tag = await consume_command(
        lookup_queue,
        command_session_factory,
        _signalling(handle_lookup_capture_command, looked_up_event),
    )
    try:
        capture_command = _capture_command(authorization_id)
        capture_key = str(capture_command.command_id)
        await publish_command(exchange, capture_command, timeout_seconds=5.0)
        await asyncio.wait_for(captured_event.wait(), timeout=5)
        await _wait_for_row(
            command_session_factory,
            authorization_id,
            status="capture_unknown",
            capture_idempotency_key=capture_key,
        )
        assert (
            await _outbox_row_count(
                command_session_factory, "payment.capture_unknown.v1", authorization_id
            )
            == 1
        )

        await publish_command(
            exchange, _lookup_capture_command(capture_key), timeout_seconds=5.0
        )
        await asyncio.wait_for(looked_up_event.wait(), timeout=5)

        await _wait_for_row(
            command_session_factory,
            authorization_id,
            status="captured",
            capture_idempotency_key=capture_key,
        )
        assert (
            await _outbox_row_count(
                command_session_factory, "payment.captured.v1", authorization_id
            )
            == 1
        )
        assert spy_psp.lookup_capture_calls == [("unknown_capture", capture_key)]
        assert len(spy_psp.capture_calls) == 1
    finally:
        await capture_queue.cancel(capture_tag)
        await lookup_queue.cancel(lookup_tag)


async def test_confirmed_absence_emits_not_found_and_allows_a_new_capture(
    channel: AbstractChannel,
    command_session_factory: async_sessionmaker[AsyncSession],
    spy_psp: _SpyPspAdapter,
) -> None:
    spy_psp.lookup_outcome = PspCaptureLookupOutcome.NOT_FOUND
    capture_queue = await declare_command_topology(channel, "payment.capture.v1")
    lookup_queue = await declare_command_topology(channel, "payment.lookup_capture.v1")
    await capture_queue.purge()
    await lookup_queue.purge()
    exchange = await channel.get_exchange(COMMANDS_EXCHANGE_NAME)
    authorization_id = await _seed_authorization(
        command_session_factory, "unknown_capture"
    )
    captured_event = asyncio.Event()
    looked_up_event = asyncio.Event()

    capture_tag = await consume_command(
        capture_queue,
        command_session_factory,
        _signalling(handle_capture_command, captured_event),
    )
    lookup_tag = await consume_command(
        lookup_queue,
        command_session_factory,
        _signalling(handle_lookup_capture_command, looked_up_event),
    )
    try:
        first_capture = _capture_command(authorization_id)
        first_key = str(first_capture.command_id)
        await publish_command(exchange, first_capture, timeout_seconds=5.0)
        await asyncio.wait_for(captured_event.wait(), timeout=5)
        await _wait_for_row(
            command_session_factory,
            authorization_id,
            status="capture_unknown",
            capture_idempotency_key=first_key,
        )

        await publish_command(
            exchange, _lookup_capture_command(first_key), timeout_seconds=5.0
        )
        await asyncio.wait_for(looked_up_event.wait(), timeout=5)
        await _wait_for_row(
            command_session_factory,
            authorization_id,
            status="authorized",
            capture_idempotency_key=first_key,
        )
        assert (
            await _outbox_row_count(
                command_session_factory,
                "payment.capture_not_found.v1",
                authorization_id,
            )
            == 1
        )

        # Absence confirmed — a capture with a new key reaches the PSP again
        # (DoD 3). The Test PSP answers `unknown_capture` with UNKNOWN again.
        captured_event.clear()
        second_capture = _capture_command(authorization_id)
        second_key = str(second_capture.command_id)
        await publish_command(exchange, second_capture, timeout_seconds=5.0)
        await asyncio.wait_for(captured_event.wait(), timeout=5)
        await _wait_for_row(
            command_session_factory,
            authorization_id,
            status="capture_unknown",
            capture_idempotency_key=second_key,
        )
        assert spy_psp.capture_calls == [
            ("unknown_capture", first_key),
            ("unknown_capture", second_key),
        ]
    finally:
        await capture_queue.cancel(capture_tag)
        await lookup_queue.cancel(lookup_tag)


async def test_duplicate_capture_command_id_redelivery_calls_the_psp_once(
    channel: AbstractChannel,
    command_session_factory: async_sessionmaker[AsyncSession],
    spy_psp: _SpyPspAdapter,
) -> None:
    queue = await declare_command_topology(channel, "payment.capture.v1")
    await queue.purge()
    exchange = await channel.get_exchange(COMMANDS_EXCHANGE_NAME)
    authorization_id = await _seed_authorization(command_session_factory, "success")
    command = _capture_command(authorization_id)
    handled = asyncio.Event()

    consumer_tag = await consume_command(
        queue, command_session_factory, _signalling(handle_capture_command, handled)
    )
    try:
        await publish_command(exchange, command, timeout_seconds=5.0)
        await asyncio.wait_for(handled.wait(), timeout=5)
        await _wait_for_row(
            command_session_factory,
            authorization_id,
            status="captured",
            capture_idempotency_key=str(command.command_id),
        )

        # Redeliver the exact same command_id — the inbox gate must ACK it
        # without re-invoking the handler at all.
        await publish_command(exchange, command, timeout_seconds=5.0)
        await asyncio.sleep(0.3)

        async with command_session_factory() as session:
            inbox_count = await session.scalar(
                select(func.count())
                .select_from(InboxMessage)
                .where(InboxMessage.command_id == command.command_id)
            )
        assert inbox_count == 1
        assert (
            await _outbox_row_count(
                command_session_factory, "payment.captured.v1", authorization_id
            )
            == 1
        )
        assert len(spy_psp.capture_calls) == 1
    finally:
        await queue.cancel(consumer_tag)
