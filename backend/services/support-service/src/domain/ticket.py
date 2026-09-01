import uuid
from dataclasses import dataclass
from datetime import datetime
from enum import StrEnum

from kernel_domain.entity import Entity

from domain.events.ticket_created import TicketCreated
from domain.message import TicketMessage, validate_plaintext


class TicketStatus(StrEnum):
    OPEN = "OPEN"
    IN_PROGRESS = "IN_PROGRESS"
    RESOLVED = "RESOLVED"
    CLOSED = "CLOSED"


@dataclass(slots=True)
class Ticket(Entity[uuid.UUID]):
    author_id: uuid.UUID
    subject: str
    status: TicketStatus
    messages: list[TicketMessage]
    created_at: datetime

    def __init__(
        self,
        id: uuid.UUID,
        *,
        author_id: uuid.UUID,
        subject: str,
        status: TicketStatus = TicketStatus.OPEN,
        messages: list[TicketMessage] | None = None,
        created_at: datetime | None = None,
    ) -> None:
        Entity.__init__(self, id)
        self.author_id = author_id
        self.subject = validate_plaintext(subject, field_name="subject", maximum=200)
        self.status = status
        self.messages = messages or []
        if not self.messages:
            raise ValueError("ticket must have a first message")
        first = self.messages[0]
        if first.ticket_id != self.id or first.author_id != self.author_id:
            raise ValueError("first message must belong to the ticket author")
        self.created_at = created_at or first.created_at

    @classmethod
    def create(
        cls, *, author_id: uuid.UUID, subject: str, first_message: str
    ) -> "Ticket":
        ticket_id = uuid.uuid4()
        ticket = object.__new__(cls)
        Entity.__init__(ticket, ticket_id)
        ticket.author_id = author_id
        ticket.subject = validate_plaintext(subject, field_name="subject", maximum=200)
        ticket.status = TicketStatus.OPEN
        ticket.messages = [
            TicketMessage(
                id=uuid.uuid4(),
                ticket_id=ticket_id,
                author_id=author_id,
                body=validate_plaintext(
                    first_message, field_name="first_message", maximum=10_000
                ),
            )
        ]
        ticket.created_at = ticket.messages[0].created_at
        ticket.add_domain_event(TicketCreated(ticket_id=ticket_id, author_id=author_id))
        return ticket
