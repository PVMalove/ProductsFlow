import uuid
from dataclasses import dataclass

from kernel_domain.domain_event import DomainEvent


@dataclass(frozen=True, kw_only=True)
class TicketStatusChanged(DomainEvent):
    ticket_id: uuid.UUID
    previous_status: str
    status: str
    actor_category: str
    event_type: str = "ticket.status_changed.v1"
