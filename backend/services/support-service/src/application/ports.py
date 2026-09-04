# ruff: noqa: E501
"""Application-порты для command- и query-сторон support."""

import uuid
from dataclasses import dataclass
from typing import Protocol

from domain.entities.ticket import Ticket
from domain.repositories import Cursor, MessagePage, TicketPage
from domain.value_objects.ticket_id import TicketId


@dataclass(frozen=True)
class UserProjectionSnapshot:
    """Локальная event-driven копия identity User (ADR 0012) — единственный
    источник роли/статуса `Actor` у support, поэтому BFF-аутентификация
    никогда не вызывает identity синхронно на каждый запрос."""

    user_id: uuid.UUID
    role: str
    is_active: bool
    deleted: bool
    last_applied_outbox_id: int


class UserProjectionPort(Protocol):
    async def get(self, user_id: uuid.UUID) -> UserProjectionSnapshot | None: ...


class TicketQueryPort(Protocol):
    """Операции персистентности только для чтения, используемые query handler'ами."""

    async def get_for_author(
        self, ticket_id: TicketId, author_id: uuid.UUID
    ) -> Ticket | None: ...

    async def get_by_id(self, ticket_id: TicketId) -> Ticket | None: ...

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
        ticket_id: TicketId,
        limit: int,
        after: Cursor | None = None,
        before: Cursor | None = None,
    ) -> MessagePage: ...


__all__ = [
    "TicketQueryPort",
    "UserProjectionPort",
    "UserProjectionSnapshot",
]
