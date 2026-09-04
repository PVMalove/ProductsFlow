import uuid
from dataclasses import dataclass
from typing import Any

from kernel_domain.domain_event import DomainEvent

from domain.value_objects.ticket_id import TicketId


@dataclass(frozen=True, kw_only=True)
class TicketEvent(DomainEvent):
    """Общий контракт событий агрегата Ticket для transactional outbox."""

    aggregate_type: str = "Ticket"
    ticket_id: TicketId

    def aggregate_id(self) -> uuid.UUID:
        return self.ticket_id.value

    def to_payload(self) -> dict[str, Any]:
        return {"ticket_id": str(self.ticket_id.value)}


@dataclass(frozen=True, kw_only=True)
class TicketCreated(TicketEvent):
    author_id: uuid.UUID
    event_type: str = "ticket.created.v1"

    def to_payload(self) -> dict[str, Any]:
        return {**super().to_payload(), "author_id": str(self.author_id)}


@dataclass(frozen=True, kw_only=True)
class TicketMessageAdded(TicketEvent):
    message_id: uuid.UUID
    actor_category: str
    event_type: str = "ticket.message_added.v1"

    def to_payload(self) -> dict[str, Any]:
        return {
            **super().to_payload(),
            "message_id": str(self.message_id),
            "actor_category": self.actor_category,
        }


@dataclass(frozen=True, kw_only=True)
class TicketMessageEdited(TicketEvent):
    message_id: uuid.UUID
    actor_category: str
    event_type: str = "ticket.message_edited.v1"

    def to_payload(self) -> dict[str, Any]:
        return {
            **super().to_payload(),
            "message_id": str(self.message_id),
            "actor_category": self.actor_category,
        }


@dataclass(frozen=True, kw_only=True)
class TicketMessageDeleted(TicketEvent):
    message_id: uuid.UUID
    actor_category: str
    event_type: str = "ticket.message_deleted.v1"

    def to_payload(self) -> dict[str, Any]:
        return {
            **super().to_payload(),
            "message_id": str(self.message_id),
            "actor_category": self.actor_category,
        }


@dataclass(frozen=True, kw_only=True)
class TicketStatusChanged(TicketEvent):
    previous_status: str
    status: str
    actor_category: str
    event_type: str = "ticket.status_changed.v1"

    def to_payload(self) -> dict[str, Any]:
        return {
            **super().to_payload(),
            "previous_status": self.previous_status,
            "status": self.status,
            "actor_category": self.actor_category,
        }
