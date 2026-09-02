"""Application ports for the support command and query sides."""

import uuid
from typing import Protocol

from domain.repositories import Cursor, MessagePage, TicketPage
from domain.ticket import Ticket


class TicketCommandPort(Protocol):
    """Transactional persistence operations used by command handlers."""

    async def create(self, ticket: Ticket) -> Ticket: ...


class TicketQueryPort(Protocol):
    """Read-only persistence operations used by query handlers."""

    async def get_for_author(
        self, ticket_id: uuid.UUID, author_id: uuid.UUID
    ) -> Ticket | None: ...

    async def get_by_id(self, ticket_id: uuid.UUID) -> Ticket | None: ...

    async def list_for_author(
        self,
        *,
        author_id: uuid.UUID,
        limit: int,
        after: Cursor | None = None,
        before: Cursor | None = None,
    ) -> TicketPage: ...

    async def list_all(
        self,
        *,
        limit: int,
        after: Cursor | None = None,
        before: Cursor | None = None,
    ) -> TicketPage: ...

    async def list_messages(
        self,
        *,
        ticket_id: uuid.UUID,
        limit: int,
        after: Cursor | None = None,
        before: Cursor | None = None,
    ) -> MessagePage: ...


__all__ = ["TicketCommandPort", "TicketQueryPort"]
