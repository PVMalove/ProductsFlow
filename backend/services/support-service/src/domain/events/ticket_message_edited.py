import uuid
from dataclasses import dataclass

from kernel_domain.domain_event import DomainEvent


@dataclass(frozen=True, kw_only=True)
class TicketMessageEdited(DomainEvent):
    ticket_id: uuid.UUID
    message_id: uuid.UUID
    actor_category: str
    event_type: str = "ticket.message_edited.v1"
