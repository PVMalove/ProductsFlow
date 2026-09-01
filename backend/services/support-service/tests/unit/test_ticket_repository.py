import uuid

import pytest

from domain.ticket import Ticket
from infrastructure.db.ticket_repository import SqlTicketRepository


class RecordingSession:
    def __init__(self) -> None:
        self.added: list[object] = []
        self.commit_count = 0

    def add(self, value: object) -> None:
        self.added.append(value)

    async def commit(self) -> None:
        self.commit_count += 1

    async def flush(self) -> None:
        pass


@pytest.mark.asyncio
async def test_create_adds_ticket_message_and_outbox_before_one_commit() -> None:
    session = RecordingSession()
    ticket = Ticket.create(
        author_id=uuid.uuid4(), subject="Subject", first_message="Message"
    )

    await SqlTicketRepository(session).create(ticket)  # type: ignore[arg-type]

    assert {type(item).__name__ for item in session.added} == {
        "TicketModel",
        "TicketMessageModel",
        "OutboxMessage",
    }
    assert session.commit_count == 1
