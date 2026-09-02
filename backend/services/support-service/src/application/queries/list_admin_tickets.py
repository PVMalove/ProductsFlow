"""List-all-tickets query and handler."""

from dataclasses import dataclass

from application.ports import TicketQueryPort
from domain.repositories import Cursor, TicketPage


@dataclass(frozen=True)
class ListAdminTicketsQuery:
    limit: int
    after: Cursor | None = None
    before: Cursor | None = None


class ListAdminTicketsQueryHandler:
    def __init__(self, repository: TicketQueryPort) -> None:
        self._repository = repository

    async def handle(self, query: ListAdminTicketsQuery) -> TicketPage:
        return await self._repository.list_all(
            limit=query.limit,
            after=query.after,
            before=query.before,
        )
