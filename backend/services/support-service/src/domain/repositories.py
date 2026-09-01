from typing import Protocol

from domain.ticket import Ticket


class TicketRepository(Protocol):
    async def create(self, ticket: Ticket) -> Ticket: ...
