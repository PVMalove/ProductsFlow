"""List-owned-tickets query and handler."""

import uuid
from dataclasses import dataclass

from application.ports import TicketQueryPort
from domain.repositories import Cursor, TicketPage


@dataclass(frozen=True)
class ListTicketsQuery:
    author_id: uuid.UUID
    limit: int
    after: Cursor | None = None
    before: Cursor | None = None


class ListTicketsQueryHandler:
    def __init__(self, repository: TicketQueryPort) -> None:
        self._repository = repository

    async def handle(self, query: ListTicketsQuery) -> TicketPage:
        return await self._repository.list_for_author(
            author_id=query.author_id,
            limit=query.limit,
            after=query.after,
            before=query.before,
        )
