"""Get-ticket query and visibility handler."""

import uuid
from dataclasses import dataclass

from application.ports import TicketQueryPort
from domain.ticket import Ticket


@dataclass(frozen=True)
class GetTicketQuery:
    ticket_id: uuid.UUID
    author_id: uuid.UUID
    is_admin: bool = False


class GetTicketQueryHandler:
    def __init__(self, repository: TicketQueryPort) -> None:
        self._repository = repository

    async def handle(self, query: GetTicketQuery) -> Ticket | None:
        if query.is_admin:
            return await self._repository.get_by_id(query.ticket_id)
        return await self._repository.get_for_author(query.ticket_id, query.author_id)
