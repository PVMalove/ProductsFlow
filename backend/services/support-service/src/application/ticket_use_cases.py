import uuid

from domain.repositories import Cursor, MessagePage, TicketPage, TicketRepository
from domain.ticket import Ticket


class CreateTicket:
    def __init__(self, repository: TicketRepository) -> None:
        self._repository = repository

    async def execute(
        self, *, author_id: uuid.UUID, subject: str, first_message: str
    ) -> Ticket:
        ticket = Ticket.create(
            author_id=author_id, subject=subject, first_message=first_message
        )
        return await self._repository.create(ticket)


class GetTicket:
    def __init__(self, repository: TicketRepository) -> None:
        self._repository = repository

    async def execute(
        self, *, ticket_id: uuid.UUID, author_id: uuid.UUID, is_admin: bool = False
    ) -> Ticket | None:
        if is_admin:
            return await self._repository.get_by_id(ticket_id)
        return await self._repository.get_for_author(ticket_id, author_id)

    async def messages(
        self,
        *,
        ticket_id: uuid.UUID,
        limit: int,
        after: Cursor | None = None,
        before: Cursor | None = None,
    ) -> MessagePage:
        return await self._repository.list_messages(
            ticket_id=ticket_id, limit=limit, after=after, before=before
        )


class ListTickets:
    def __init__(self, repository: TicketRepository) -> None:
        self._repository = repository

    async def execute(
        self,
        *,
        author_id: uuid.UUID,
        limit: int,
        after: Cursor | None = None,
        before: Cursor | None = None,
    ) -> TicketPage:
        return await self._repository.list_for_author(
            author_id=author_id, limit=limit, after=after, before=before
        )


class ListAdminTickets(ListTickets):
    async def execute(
        self,
        *,
        author_id: uuid.UUID,
        limit: int,
        after: Cursor | None = None,
        before: Cursor | None = None,
    ) -> TicketPage:
        return await self._repository.list_all(limit=limit, after=after, before=before)
