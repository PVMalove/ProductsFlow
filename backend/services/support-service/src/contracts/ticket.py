"""Framework-independent output contracts for support BFF endpoints
(ADR 0033) — application handlers return these, HTTP only serializes them."""

import uuid
from dataclasses import dataclass
from datetime import datetime

from domain.entities.ticket import Ticket
from domain.entities.ticket_message import TicketMessage
from domain.ticket_status import TicketStatus


@dataclass(frozen=True)
class TicketMessageView:
    id: uuid.UUID
    author_id: uuid.UUID | None
    body: str
    created_at: datetime
    is_system: bool
    is_deleted: bool

    @classmethod
    def from_domain(cls, message: TicketMessage) -> "TicketMessageView":
        return cls(
            id=message.id,
            author_id=message.author_id,
            body=message.body,
            created_at=message.created_at,
            is_system=message.is_system,
            is_deleted=message.is_deleted,
        )


@dataclass(frozen=True)
class TicketView:
    """A ticket's own fields — no messages. Used by list items and by
    mutation responses; ticket detail is `TicketDetailView` instead."""

    id: uuid.UUID
    author_id: uuid.UUID | None
    subject: str
    status: TicketStatus
    created_at: datetime

    @classmethod
    def from_domain(cls, ticket: Ticket) -> "TicketView":
        return cls(
            id=ticket.id.value,
            author_id=ticket.author_id,
            subject=ticket.subject,
            status=ticket.status,
            created_at=ticket.created_at,
        )


@dataclass(frozen=True)
class TicketDetailView:
    id: uuid.UUID
    author_id: uuid.UUID | None
    subject: str
    status: TicketStatus
    created_at: datetime
    messages: list[TicketMessageView]

    @classmethod
    def from_domain(
        cls, ticket: Ticket, messages: list[TicketMessage]
    ) -> "TicketDetailView":
        return cls(
            id=ticket.id.value,
            author_id=ticket.author_id,
            subject=ticket.subject,
            status=ticket.status,
            created_at=ticket.created_at,
            messages=[TicketMessageView.from_domain(message) for message in messages],
        )
