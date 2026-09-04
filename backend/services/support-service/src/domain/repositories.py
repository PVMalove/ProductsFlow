import uuid
from dataclasses import dataclass
from datetime import datetime
from typing import Protocol

from domain.entities.ticket import Ticket
from domain.entities.ticket_message import TicketMessage
from domain.ticket_status import TicketStatus
from domain.value_objects.ticket_id import TicketId


class TicketRepository(Protocol):
    """Full ticket repository contract — query methods plus the serialized
    mutation operations used by command handlers through `SupportUnitOfWork`
    (ADR 0034)."""

    async def create(self, ticket: Ticket) -> Ticket: ...

    async def process_user_deleted(
        self, *, message_id: int, user_id: uuid.UUID
    ) -> bool: ...

    async def add_message(
        self,
        *,
        ticket_id: TicketId,
        actor_id: uuid.UUID,
        body: str,
        is_admin: bool,
    ) -> Ticket | None: ...

    async def change_status(
        self, *, ticket_id: TicketId, actor_id: uuid.UUID, status: TicketStatus
    ) -> Ticket | None: ...

    async def edit_message(
        self,
        *,
        ticket_id: TicketId,
        message_id: uuid.UUID,
        actor_id: uuid.UUID,
        body: str,
        is_admin: bool = False,
    ) -> Ticket | None: ...

    async def delete_message(
        self,
        *,
        ticket_id: TicketId,
        message_id: uuid.UUID,
        actor_id: uuid.UUID,
        is_admin: bool,
    ) -> Ticket | None: ...

    async def get_for_author(
        self, ticket_id: TicketId, author_id: uuid.UUID
    ) -> Ticket | None: ...

    async def get_by_id(self, ticket_id: TicketId) -> Ticket | None: ...

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
        ticket_id: TicketId,
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
