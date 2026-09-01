import uuid
from collections.abc import AsyncIterator

import pytest
import pytest_asyncio
from kernel_platform.outbox.models import Base, OutboxMessage
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncEngine, AsyncSession

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
