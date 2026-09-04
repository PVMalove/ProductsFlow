# ruff: noqa: E501
"""Application ports for the support command and query sides."""

import uuid
from dataclasses import dataclass
from typing import Protocol

from domain.repositories import Cursor, MessagePage, TicketPage
from domain.ticket import Ticket


@dataclass(frozen=True)
class UserProjectionSnapshot:
    """Local, event-driven copy of an identity User (ADR 0033) — support's
    only source of `Actor` role/status, so BFF authentication never calls
    identity synchronously per request."""

    user_id: uuid.UUID
    role: str
    is_active: bool
    deleted: bool
    last_applied_outbox_id: int


class UserProjectionPort(Protocol):
    async def get(self, user_id: uuid.UUID) -> UserProjectionSnapshot | None: ...


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


__all__ = [
    "TicketQueryPort",
    "UserProjectionPort",
    "UserProjectionSnapshot",
]
