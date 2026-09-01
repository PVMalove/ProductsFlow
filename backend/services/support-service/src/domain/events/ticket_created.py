import uuid
from dataclasses import dataclass

from kernel_domain.domain_event import DomainEvent


@dataclass(frozen=True, kw_only=True)
class TicketCreated(DomainEvent):
    ticket_id: uuid.UUID
    author_id: uuid.UUID
    event_type: str = "ticket.created.v1"
