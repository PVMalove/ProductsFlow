import uuid

import pytest

from application.commands import CreateTicketCommand, CreateTicketCommandHandler
from application.ports import TicketCommandPort, TicketQueryPort
from application.queries import (
    GetTicketQuery,
    GetTicketQueryHandler,
    ListAdminTicketsQuery,
    ListAdminTicketsQueryHandler,
    ListTicketMessagesQuery,
    ListTicketMessagesQueryHandler,
    ListTicketsQuery,
    ListTicketsQueryHandler,
)
from contracts.ticket import TicketDetailView
from domain.repositories import MessagePage, PageInfo, TicketPage
from domain.ticket import Ticket


class FakeTicketRepository:
    def __init__(self) -> None:
        self.created: Ticket | None = None
        self.ticket: Ticket | None = None
        self.ticket_page = TicketPage([], PageInfo(None, None, False, False))
        self.message_page = MessagePage([], PageInfo(None, None, False, False))

    async def create(self, ticket: Ticket) -> Ticket:
        self.created = ticket
        return ticket

    async def get_for_author(
        self, ticket_id: uuid.UUID, author_id: uuid.UUID
    ) -> Ticket | None:
        if self.ticket is not None and self.ticket.id == ticket_id:
            return self.ticket if self.ticket.author_id == author_id else None
        return None

    async def get_by_id(self, ticket_id: uuid.UUID) -> Ticket | None:
        return (
            self.ticket
            if self.ticket is not None and self.ticket.id == ticket_id
            else None
        )

    async def list_for_author(
        self,
        *,
        author_id: uuid.UUID,
        limit: int,
        after: object = None,
        before: object = None,
    ) -> TicketPage:
        return self.ticket_page

    async def list_all(
        self,
        *,
        limit: int,
        after: object = None,
        before: object = None,
    ) -> TicketPage:
        return self.ticket_page

    async def list_messages(
        self,
        *,
        ticket_id: uuid.UUID,
        limit: int,
        after: object = None,
        before: object = None,
    ) -> MessagePage:
        return self.message_page


@pytest.mark.asyncio
async def test_create_ticket_command_uses_the_command_port() -> None:
    repository = FakeTicketRepository()
    author_id = uuid.uuid4()

    result = await CreateTicketCommandHandler(repository).execute(
        CreateTicketCommand(
            author_id=author_id,
            subject="Subject",
            first_message="Message",
        )
    )

    assert result.is_ok
    assert result.value.author_id == author_id
    assert repository.created is not None
    assert result.value == TicketDetailView.from_domain(
        repository.created, repository.created.messages
    )


@pytest.mark.asyncio
async def test_ticket_queries_are_independent_handlers() -> None:
    repository = FakeTicketRepository()
    author_id = uuid.uuid4()
    ticket = Ticket.create(
        author_id=author_id, subject="Subject", first_message="Message"
    )
    repository.ticket = ticket
    repository.ticket_page = TicketPage([ticket], PageInfo(None, None, False, False))

    assert (
        await GetTicketQueryHandler(repository).execute(
            GetTicketQuery(ticket_id=ticket.id, author_id=author_id)
        )
    ) is ticket
    assert (
        await ListTicketsQueryHandler(repository).execute(
            ListTicketsQuery(author_id=author_id, limit=20)
        )
    ).items == [ticket]
    admin_result = await ListAdminTicketsQueryHandler(repository).execute(
        ListAdminTicketsQuery(limit=20, is_admin=True)
    )
    assert admin_result.is_ok
    assert admin_result.value.items == [ticket]
    assert (
        await ListTicketMessagesQueryHandler(repository).execute(
            ListTicketMessagesQuery(ticket_id=ticket.id, limit=20)
        )
    ) == repository.message_page


@pytest.mark.asyncio
async def test_list_admin_tickets_forbids_a_non_admin_actor() -> None:
    repository = FakeTicketRepository()

    result = await ListAdminTicketsQueryHandler(repository).execute(
        ListAdminTicketsQuery(limit=20, is_admin=False)
    )

    assert result.is_err
    assert result.error.code == "FORBIDDEN"


def test_support_cqrs_handlers_expose_execute_only() -> None:
    handler_types = (
        CreateTicketCommandHandler,
        GetTicketQueryHandler,
        ListTicketsQueryHandler,
        ListAdminTicketsQueryHandler,
        ListTicketMessagesQueryHandler,
    )

    assert all(hasattr(handler_type, "execute") for handler_type in handler_types)
    assert all(not hasattr(handler_type, "handle") for handler_type in handler_types)
    assert TicketCommandPort is not TicketQueryPort
