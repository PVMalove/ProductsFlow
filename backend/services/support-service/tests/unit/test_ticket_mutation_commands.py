import uuid

import pytest

from application.commands import (
    AddTicketMessageCommand,
    AddTicketMessageCommandHandler,
    ChangeTicketStatusCommand,
    ChangeTicketStatusCommandHandler,
    DeleteTicketMessageCommand,
    DeleteTicketMessageCommandHandler,
    EditTicketMessageCommand,
    EditTicketMessageCommandHandler,
)
from domain.ticket import Ticket, TicketStatus


class FakeMutationRepository:
    def __init__(self, ticket: Ticket | None) -> None:
        self.ticket = ticket
        self.message_calls: list[tuple[uuid.UUID, bool]] = []
        self.status_calls: list[tuple[uuid.UUID, TicketStatus]] = []
        self.edit_calls: list[tuple[uuid.UUID, uuid.UUID, str, bool]] = []
        self.delete_calls: list[tuple[uuid.UUID, uuid.UUID, bool]] = []

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

    async def edit_message(
        self,
        *,
        ticket_id: uuid.UUID,
        message_id: uuid.UUID,
        actor_id: uuid.UUID,
        body: str,
        is_admin: bool = False,
    ) -> Ticket | None:
        self.edit_calls.append((ticket_id, message_id, body, is_admin))
        return self.ticket

    async def delete_message(
        self,
        *,
        ticket_id: uuid.UUID,
        message_id: uuid.UUID,
        actor_id: uuid.UUID,
        is_admin: bool,
    ) -> Ticket | None:
        self.delete_calls.append((ticket_id, message_id, is_admin))
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

    assert result.is_ok
    assert result.value is ticket
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
            is_admin=True,
        )
    )

    assert result.is_ok
    assert result.value is ticket
    assert repository.status_calls == [(actor_id, TicketStatus.IN_PROGRESS)]


@pytest.mark.asyncio
async def test_change_status_command_forbids_a_non_admin_actor() -> None:
    ticket = Ticket.create(
        author_id=uuid.uuid4(), subject="Subject", first_message="First message"
    )
    repository = FakeMutationRepository(ticket)

    result = await ChangeTicketStatusCommandHandler(repository).execute(
        ChangeTicketStatusCommand(
            ticket_id=ticket.id,
            actor_id=uuid.uuid4(),
            status=TicketStatus.IN_PROGRESS,
            is_admin=False,
        )
    )

    assert result.is_err
    assert result.error.code == "FORBIDDEN"
    assert repository.status_calls == []


@pytest.mark.asyncio
async def test_edit_message_command_passes_message_and_new_body() -> None:
    ticket = Ticket.create(
        author_id=uuid.uuid4(), subject="Subject", first_message="First message"
    )
    repository = FakeMutationRepository(ticket)
    message_id = ticket.messages[0].id
    assert ticket.author_id is not None

    result = await EditTicketMessageCommandHandler(repository).execute(
        EditTicketMessageCommand(
            ticket_id=ticket.id,
            message_id=message_id,
            actor_id=ticket.author_id,
            body="Corrected",
            is_admin=True,
        )
    )

    assert result.is_ok
    assert result.value is ticket
    assert repository.edit_calls == [(ticket.id, message_id, "Corrected", True)]


@pytest.mark.asyncio
async def test_delete_message_command_passes_admin_moderation_context() -> None:
    ticket = Ticket.create(
        author_id=uuid.uuid4(), subject="Subject", first_message="First message"
    )
    repository = FakeMutationRepository(ticket)
    message_id = ticket.messages[0].id

    result = await DeleteTicketMessageCommandHandler(repository).execute(
        DeleteTicketMessageCommand(
            ticket_id=ticket.id,
            message_id=message_id,
            actor_id=uuid.uuid4(),
            is_admin=True,
        )
    )

    assert result.is_ok
    assert result.value is ticket
    assert repository.delete_calls == [(ticket.id, message_id, True)]
