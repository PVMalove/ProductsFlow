import uuid

import pytest

from application.commands import (
    AddTicketMessageCommand,
    AddTicketMessageCommandHandler,
    ChangeTicketStatusCommand,
    ChangeTicketStatusCommandHandler,
)
from domain.ticket import Ticket, TicketStatus


class FakeMutationRepository:
    def __init__(self, ticket: Ticket | None) -> None:
        self.ticket = ticket
        self.message_calls: list[tuple[uuid.UUID, bool]] = []
        self.status_calls: list[tuple[uuid.UUID, TicketStatus]] = []

    async def add_message(
        self, *, ticket_id: uuid.UUID, actor_id: uuid.UUID, body: str, is_admin: bool
    ) -> Ticket | None:
        self.message_calls.append((actor_id, is_admin))
        return self.ticket

    async def change_status(
        self, *, ticket_id: uuid.UUID, actor_id: uuid.UUID, status: TicketStatus
    ) -> Ticket | None:
        self.status_calls.append((actor_id, status))
        return self.ticket


@pytest.mark.asyncio
async def test_add_message_command_passes_actor_category_to_repository() -> None:
    ticket = Ticket.create(
        author_id=uuid.uuid4(), subject="Subject", first_message="First message"
    )
    repository = FakeMutationRepository(ticket)
    actor_id = uuid.uuid4()

    result = await AddTicketMessageCommandHandler(repository).execute(
        AddTicketMessageCommand(
            ticket_id=ticket.id,
            actor_id=actor_id,
            body="Reply",
            is_admin=True,
        )
    )

    assert result is ticket
    assert repository.message_calls == [(actor_id, True)]


@pytest.mark.asyncio
async def test_change_status_command_passes_requested_status_to_repository() -> None:
    ticket = Ticket.create(
        author_id=uuid.uuid4(), subject="Subject", first_message="First message"
    )
    repository = FakeMutationRepository(ticket)
    actor_id = uuid.uuid4()

    result = await ChangeTicketStatusCommandHandler(repository).execute(
        ChangeTicketStatusCommand(
            ticket_id=ticket.id,
            actor_id=actor_id,
            status=TicketStatus.IN_PROGRESS,
        )
    )

    assert result is ticket
    assert repository.status_calls == [(actor_id, TicketStatus.IN_PROGRESS)]
