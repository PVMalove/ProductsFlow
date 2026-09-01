import uuid
from dataclasses import dataclass
from datetime import datetime
from typing import Protocol

from domain.message import TicketMessage
from domain.ticket import Ticket


class TicketRepository(Protocol):
    async def create(self, ticket: Ticket) -> Ticket: ...

    async def get_for_author(
        self, ticket_id: uuid.UUID, author_id: uuid.UUID
    ) -> Ticket | None: ...

    async def get_by_id(self, ticket_id: uuid.UUID) -> Ticket | None: ...

    async def list_for_author(
        self,
        *,
        author_id: uuid.UUID,
        limit: int,
        after: "Cursor | None" = None,
        before: "Cursor | None" = None,
    ) -> "TicketPage": ...

    async def list_all(
        self,
        *,
        limit: int,
        after: "Cursor | None" = None,
        before: "Cursor | None" = None,
    ) -> "TicketPage": ...

    async def list_messages(
        self,
        *,
        ticket_id: uuid.UUID,
        limit: int,
        after: "Cursor | None" = None,
        before: "Cursor | None" = None,
    ) -> "MessagePage": ...


@dataclass(frozen=True, slots=True)
class Cursor:
    created_at: datetime
    id: uuid.UUID


@dataclass(frozen=True, slots=True)
class PageInfo:
    next_cursor: str | None
    prev_cursor: str | None
    has_more: bool
    has_prev: bool


@dataclass(frozen=True, slots=True)
class TicketPage:
    items: list[Ticket]
    page_info: PageInfo


@dataclass(frozen=True, slots=True)
class MessagePage:
    items: list[TicketMessage]
    page_info: PageInfo
