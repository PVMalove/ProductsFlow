import uuid
from dataclasses import dataclass
from datetime import datetime
from enum import StrEnum

from kernel_domain.entity import Entity

from domain.events.ticket_created import TicketCreated
from domain.events.ticket_message_added import TicketMessageAdded
from domain.events.ticket_status_changed import TicketStatusChanged
from domain.message import TicketMessage, validate_plaintext


class TicketClosedError(ValueError):
    """Raised when a normal mutation targets a terminal ticket."""


class InvalidStatusTransitionError(ValueError):
    """Raised when a status skips or reverses the normal lifecycle."""


class TicketStatus(StrEnum):
    OPEN = "OPEN"
    IN_PROGRESS = "IN_PROGRESS"
    RESOLVED = "RESOLVED"
    CLOSED = "CLOSED"


_NEXT_STATUS = {
    TicketStatus.OPEN: TicketStatus.IN_PROGRESS,
    TicketStatus.IN_PROGRESS: TicketStatus.RESOLVED,
    TicketStatus.RESOLVED: TicketStatus.CLOSED,
}


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

    def add_message(
        self, *, author_id: uuid.UUID, body: str, actor_category: str
    ) -> TicketMessage:
        if self.status is TicketStatus.CLOSED:
            raise TicketClosedError("closed tickets cannot receive messages")

        message = TicketMessage(
            id=uuid.uuid4(),
            ticket_id=self.id,
            author_id=author_id,
            body=body,
        )
        self.messages.append(message)
        self.add_domain_event(
            TicketMessageAdded(
                ticket_id=self.id,
                message_id=message.id,
                actor_category=actor_category,
            )
        )

        if (
            actor_category == "user"
            and author_id == self.author_id
            and self.status is TicketStatus.RESOLVED
        ):
            self._change_status(
                TicketStatus.IN_PROGRESS,
                actor_category=actor_category,
                allow_reopen=True,
            )
        return message

    def change_status(self, status: TicketStatus, *, actor_category: str) -> None:
        self._change_status(status, actor_category=actor_category)

    def _change_status(
        self,
        status: TicketStatus,
        *,
        actor_category: str,
        allow_reopen: bool = False,
    ) -> None:
        if self.status is TicketStatus.CLOSED:
            raise TicketClosedError("closed tickets have a terminal status")
        if not allow_reopen and _NEXT_STATUS.get(self.status) is not status:
            raise InvalidStatusTransitionError(
                f"cannot change status from {self.status} to {status}"
            )

        previous_status = self.status
        self.status = status
        self.add_domain_event(
            TicketStatusChanged(
                ticket_id=self.id,
                previous_status=previous_status.value,
                status=status.value,
                actor_category=actor_category,
            )
        )
