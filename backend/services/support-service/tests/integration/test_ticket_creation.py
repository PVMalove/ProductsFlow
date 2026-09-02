import asyncio
import uuid
from collections.abc import AsyncIterator
from datetime import UTC, datetime

import pytest
import pytest_asyncio
from kernel_platform.outbox.models import Base, OutboxMessage
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncEngine, AsyncSession, async_sessionmaker

from application.pagination import decode_cursor
from domain.ticket import (
    Ticket,
    TicketMessageImmutableError,
    TicketStatus,
)
from infrastructure.db.models import TicketMessageModel, TicketModel
from infrastructure.db.ticket_repository import SqlTicketRepository

pytestmark = pytest.mark.asyncio(loop_scope="session")


@pytest_asyncio.fixture(scope="session", loop_scope="session", autouse=True)
async def support_schema(db_engine: AsyncEngine) -> AsyncIterator[None]:
    async with db_engine.begin() as connection:
        await connection.run_sync(Base.metadata.create_all)
    try:
        yield
    finally:
        async with db_engine.begin() as connection:
            await connection.run_sync(Base.metadata.drop_all)


async def test_ticket_and_outbox_are_persisted_together(
    db_session: AsyncSession,
) -> None:
    ticket = Ticket.create(
        author_id=uuid.uuid4(), subject="Subject", first_message="Message"
    )

    await SqlTicketRepository(db_session).create(ticket)

    stored_ticket = await db_session.get(TicketModel, ticket.id)
    stored_message = await db_session.scalar(
        select(TicketMessageModel).where(TicketMessageModel.ticket_id == ticket.id)
    )
    outbox = await db_session.scalar(
        select(OutboxMessage).where(OutboxMessage.aggregate_id == ticket.id)
    )
    assert stored_ticket is not None
    assert stored_message is not None
    assert outbox is not None
    assert outbox.event_type == "ticket.created.v1"


async def test_ticket_list_is_owner_scoped_and_cursor_is_stable_for_timestamp_ties(
    db_session: AsyncSession,
) -> None:
    author_id = uuid.uuid4()
    other_author_id = uuid.uuid4()
    created_at = datetime(2026, 1, 1, tzinfo=UTC)
    tickets = [
        (uuid.uuid4(), author_id, "First"),
        (uuid.uuid4(), author_id, "Second"),
        (uuid.uuid4(), other_author_id, "Hidden"),
    ]
    for ticket_id, owner_id, subject in tickets:
        db_session.add(
            TicketModel(
                id=ticket_id,
                author_id=owner_id,
                subject=subject,
                status="OPEN",
                created_at=created_at,
            )
        )
    await db_session.flush()
    for ticket_id, owner_id, subject in tickets:
        db_session.add(
            TicketMessageModel(
                id=uuid.uuid4(),
                ticket_id=ticket_id,
                author_id=owner_id,
                body=subject,
                created_at=created_at,
            )
        )
    await db_session.commit()

    repository = SqlTicketRepository(db_session)
    first_page = await repository.list_for_author(author_id=author_id, limit=1)
    second_page = await repository.list_for_author(
        author_id=author_id,
        limit=1,
        after=decode_cursor(first_page.page_info.next_cursor or ""),
    )
    all_tickets = await repository.list_all(limit=10)

    assert len(first_page.items) == 1
    assert len(second_page.items) == 1
    assert first_page.items[0].id != second_page.items[0].id
    assert {ticket.subject for ticket in all_tickets.items} == {
        "First",
        "Second",
        "Hidden",
    }


async def test_ticket_mutations_persist_messages_statuses_and_text_free_events(
    db_session: AsyncSession,
) -> None:
    author_id = uuid.uuid4()
    ticket = Ticket.create(
        author_id=author_id, subject="Subject", first_message="First message"
    )
    repository = SqlTicketRepository(db_session)
    await repository.create(ticket)

    updated = await repository.add_message(
        ticket_id=ticket.id,
        actor_id=author_id,
        body="Follow-up message",
        is_admin=False,
    )
    assert updated is not None
    assert updated.status is TicketStatus.OPEN

    await repository.change_status(
        ticket_id=ticket.id,
        actor_id=uuid.uuid4(),
        status=TicketStatus.IN_PROGRESS,
    )
    await repository.change_status(
        ticket_id=ticket.id,
        actor_id=uuid.uuid4(),
        status=TicketStatus.RESOLVED,
    )
    reopened = await repository.add_message(
        ticket_id=ticket.id,
        actor_id=author_id,
        body="It is still broken",
        is_admin=False,
    )

    assert reopened is not None
    assert reopened.status is TicketStatus.IN_PROGRESS
    events = list(
        (
            await db_session.scalars(
                select(OutboxMessage)
                .where(OutboxMessage.aggregate_id == ticket.id)
                .order_by(OutboxMessage.id)
            )
        ).all()
    )
    assert [event.event_type for event in events] == [
        "ticket.created.v1",
        "ticket.message_added.v1",
        "ticket.status_changed.v1",
        "ticket.status_changed.v1",
        "ticket.message_added.v1",
        "ticket.status_changed.v1",
    ]
    assert all("body" not in event.payload for event in events)


async def test_non_owner_message_is_not_persisted(
    db_session: AsyncSession,
) -> None:
    author_id = uuid.uuid4()
    ticket = Ticket.create(
        author_id=author_id, subject="Subject", first_message="First message"
    )
    repository = SqlTicketRepository(db_session)
    await repository.create(ticket)

    result = await repository.add_message(
        ticket_id=ticket.id,
        actor_id=uuid.uuid4(),
        body="Should be rejected",
        is_admin=False,
    )

    assert result is None
    messages = list(
        (
            await db_session.scalars(
                select(TicketMessageModel).where(
                    TicketMessageModel.ticket_id == ticket.id
                )
            )
        ).all()
    )
    assert len(messages) == 1


async def test_concurrent_admin_messages_are_serialized(
    db_engine: AsyncEngine,
) -> None:
    session_factory = async_sessionmaker(db_engine, expire_on_commit=False)
    ticket = Ticket.create(
        author_id=uuid.uuid4(), subject="Subject", first_message="First message"
    )
    async with session_factory() as session:
        await SqlTicketRepository(session).create(ticket)

    async def append(body: str) -> Ticket | None:
        async with session_factory() as session:
            return await SqlTicketRepository(session).add_message(
                ticket_id=ticket.id,
                actor_id=uuid.uuid4(),
                body=body,
                is_admin=True,
            )

    first, second = await asyncio.gather(append("First reply"), append("Second reply"))

    assert first is not None
    assert second is not None
    async with session_factory() as session:
        messages = list(
            (
                await session.scalars(
                    select(TicketMessageModel).where(
                        TicketMessageModel.ticket_id == ticket.id
                    )
                )
            ).all()
        )
    assert {message.body for message in messages} == {
        "First message",
        "First reply",
        "Second reply",
    }


async def test_message_edit_and_admin_moderation_are_transactional(
    db_session: AsyncSession,
) -> None:
    author_id = uuid.uuid4()
    ticket = Ticket.create(
        author_id=author_id, subject="Subject", first_message="Original message"
    )
    repository = SqlTicketRepository(db_session)
    await repository.create(ticket)
    message_id = ticket.messages[0].id

    edited = await repository.edit_message(
        ticket_id=ticket.id,
        message_id=message_id,
        actor_id=author_id,
        body="Corrected message",
    )
    deleted = await repository.delete_message(
        ticket_id=ticket.id,
        message_id=message_id,
        actor_id=uuid.uuid4(),
        is_admin=True,
    )

    stored = await db_session.get(TicketMessageModel, message_id)
    events = list(
        (
            await db_session.scalars(
                select(OutboxMessage)
                .where(OutboxMessage.aggregate_id == ticket.id)
                .order_by(OutboxMessage.id)
            )
        ).all()
    )
    assert edited is not None
    assert deleted is not None
    assert stored is not None
    assert stored.body == "[Сообщение удалено]"
    assert stored.is_deleted is True
    assert [event.event_type for event in events] == [
        "ticket.created.v1",
        "ticket.message_edited.v1",
        "ticket.message_deleted.v1",
    ]
    assert all("body" not in event.payload for event in events)


async def test_author_can_edit_and_soft_delete_their_own_message(
    db_session: AsyncSession,
) -> None:
    author_id = uuid.uuid4()
    ticket = Ticket.create(
        author_id=author_id, subject="Subject", first_message="Original message"
    )
    repository = SqlTicketRepository(db_session)
    await repository.create(ticket)
    message_id = ticket.messages[0].id

    edited = await repository.edit_message(
        ticket_id=ticket.id,
        message_id=message_id,
        actor_id=author_id,
        body="Corrected message",
    )
    deleted = await repository.delete_message(
        ticket_id=ticket.id,
        message_id=message_id,
        actor_id=author_id,
        is_admin=False,
    )

    assert edited is not None
    assert deleted is not None
    stored = await db_session.get(TicketMessageModel, message_id)
    assert stored is not None
    assert stored.body == "[Сообщение удалено]"
    assert stored.is_deleted is True


async def test_admin_can_edit_their_own_message_in_a_foreign_ticket(
    db_session: AsyncSession,
) -> None:
    author_id = uuid.uuid4()
    admin_id = uuid.uuid4()
    ticket = Ticket.create(
        author_id=author_id, subject="Subject", first_message="First message"
    )
    repository = SqlTicketRepository(db_session)
    await repository.create(ticket)
    admin_message = await repository.add_message(
        ticket_id=ticket.id,
        actor_id=admin_id,
        body="Admin reply",
        is_admin=True,
    )
    assert admin_message is not None
    message_id = admin_message.messages[-1].id

    edited = await repository.edit_message(
        ticket_id=ticket.id,
        message_id=message_id,
        actor_id=admin_id,
        body="Corrected admin reply",
        is_admin=True,
    )

    assert edited is not None
    assert edited.messages[-1].body == "Corrected admin reply"


async def test_message_moderation_rejects_closed_and_system_messages(
    db_session: AsyncSession,
) -> None:
    author_id = uuid.uuid4()
    ticket = Ticket.create(
        author_id=author_id, subject="Subject", first_message="First message"
    )
    repository = SqlTicketRepository(db_session)
    await repository.create(ticket)
    await repository.change_status(
        ticket_id=ticket.id, actor_id=uuid.uuid4(), status=TicketStatus.IN_PROGRESS
    )
    await repository.change_status(
        ticket_id=ticket.id, actor_id=uuid.uuid4(), status=TicketStatus.RESOLVED
    )
    await repository.change_status(
        ticket_id=ticket.id, actor_id=uuid.uuid4(), status=TicketStatus.CLOSED
    )

    deleted = await repository.delete_message(
        ticket_id=ticket.id,
        message_id=ticket.messages[0].id,
        actor_id=uuid.uuid4(),
        is_admin=True,
    )
    assert deleted is not None

    system_ticket = Ticket.create(
        author_id=author_id, subject="System subject", first_message="First message"
    )
    await repository.create(system_ticket)
    system_message_id = uuid.uuid4()
    system_message = TicketMessageModel(
        id=system_message_id,
        ticket_id=system_ticket.id,
        author_id=uuid.uuid4(),
        body="System message",
        created_at=datetime.now(UTC),
        is_system=True,
    )
    db_session.add(system_message)
    await db_session.commit()
    with pytest.raises(TicketMessageImmutableError):
        await repository.delete_message(
            ticket_id=system_ticket.id,
            message_id=system_message_id,
            actor_id=uuid.uuid4(),
            is_admin=True,
        )

    stored_system = await db_session.get(TicketMessageModel, system_message_id)
    assert stored_system is not None
    assert stored_system.is_deleted is False
