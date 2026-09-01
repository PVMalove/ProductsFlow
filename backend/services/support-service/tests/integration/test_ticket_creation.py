import uuid
from collections.abc import AsyncIterator
from datetime import UTC, datetime

import pytest
import pytest_asyncio
from kernel_platform.outbox.models import Base, OutboxMessage
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncEngine, AsyncSession

from application.pagination import decode_cursor
from domain.ticket import Ticket
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
