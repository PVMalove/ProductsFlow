import uuid
from dataclasses import dataclass
from datetime import datetime
from enum import StrEnum

from kernel_domain.entity import Entity

from domain.events.ticket_created import TicketCreated
from domain.events.ticket_message_added import TicketMessageAdded
from domain.events.ticket_status_changed import TicketStatusChanged
from domain.message import DELETED_MESSAGE_MARKER, TicketMessage, validate_plaintext

USER_DELETED_MESSAGE = "[Пользователь удалён]"


class TicketClosedError(ValueError):
    """Raised when a normal mutation targets a terminal ticket."""


class InvalidStatusTransitionError(ValueError):
    """Raised when a status skips or reverses the normal lifecycle."""


class TicketMessageNotFoundError(LookupError):
    """Raised when a message is not part of the ticket."""


class TicketMessageImmutableError(ValueError):
    """Raised when a system message is mutated."""


class TicketMessageAlreadyDeletedError(ValueError):
    """Raised when a deleted message is mutated again."""


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
    author_id: uuid.UUID | None
    subject: str
    status: TicketStatus
    messages: list[TicketMessage]
    created_at: datetime

    def __init__(
        self,
        id: uuid.UUID,
        *,
        author_id: uuid.UUID | None,
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
        if first.ticket_id != self.id or (
            self.author_id is not None and first.author_id != self.author_id
        ):
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
        self,
        *,
        author_id: uuid.UUID,
        body: str,
        actor_category: str,
        is_system: bool = False,
    ) -> TicketMessage:
        if self.status is TicketStatus.CLOSED:
            raise TicketClosedError("closed tickets cannot receive messages")

        message = TicketMessage(
            id=uuid.uuid4(),
            ticket_id=self.id,
            author_id=author_id,
            body=body,
            is_system=is_system,
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

    def anonymize_deleted_user(self, user_id: uuid.UUID) -> bool:
        """Remove a deleted user's identity and close their active ticket.

        The deletion event is recorded by the application inbox, so this
        aggregate operation is intentionally safe to call more than once: an
        already anonymized ticket cannot receive another system message.
        """
        owns_ticket = self.author_id == user_id
        if owns_ticket:
            self.author_id = None

        for message in self.messages:
            if message.author_id == user_id:
                object.__setattr__(message, "author_id", None)

        if not owns_ticket or self.status is TicketStatus.CLOSED:
            return owns_ticket

        previous_status = self.status
        self.status = TicketStatus.CLOSED
        self.add_domain_event(
            TicketStatusChanged(
                ticket_id=self.id,
                previous_status=previous_status.value,
                status=TicketStatus.CLOSED.value,
                actor_category="system",
            )
        )
        system_message = TicketMessage(
            id=uuid.uuid4(),
            ticket_id=self.id,
            author_id=None,
            body=USER_DELETED_MESSAGE,
            is_system=True,
        )
        self.messages.append(system_message)
        self.add_domain_event(
            TicketMessageAdded(
                ticket_id=self.id,
                message_id=system_message.id,
                actor_category="system",
            )
        )
        return True

    def edit_message(
        self,
        *,
        message_id: uuid.UUID,
        author_id: uuid.UUID,
        body: str,
        actor_category: str,
    ) -> TicketMessage:
        if self.status is TicketStatus.CLOSED:
            raise TicketClosedError("closed tickets cannot edit messages")
        message = self._message_by_id(message_id)
        if message.author_id != author_id:
            raise TicketMessageNotFoundError("message is owned by another author")
        if message.is_system:
            raise TicketMessageImmutableError("system messages cannot be edited")
        if message.is_deleted:
            raise TicketMessageAlreadyDeletedError("deleted messages cannot be edited")

        object.__setattr__(
            message,
            "body",
            validate_plaintext(body, field_name="body", maximum=10_000),
        )
        from domain.events.ticket_message_edited import TicketMessageEdited

        self.add_domain_event(
            TicketMessageEdited(
                ticket_id=self.id,
                message_id=message.id,
                actor_category=actor_category,
            )
        )
        return message

    def delete_message(
        self,
        *,
        message_id: uuid.UUID,
        actor_id: uuid.UUID,
        actor_category: str,
    ) -> TicketMessage:
        if self.status is TicketStatus.CLOSED and actor_category != "admin":
            raise TicketClosedError("closed tickets cannot delete messages")
        message = self._message_by_id(message_id)
        if actor_category != "admin" and message.author_id != actor_id:
            raise TicketMessageNotFoundError("message is owned by another author")
        if message.is_system:
            raise TicketMessageImmutableError("system messages cannot be deleted")
        if message.is_deleted:
            raise TicketMessageAlreadyDeletedError("message is already deleted")

        object.__setattr__(message, "body", DELETED_MESSAGE_MARKER)
        object.__setattr__(message, "is_deleted", True)
        from domain.events.ticket_message_deleted import TicketMessageDeleted

        self.add_domain_event(
            TicketMessageDeleted(
                ticket_id=self.id,
                message_id=message.id,
                actor_category=actor_category,
            )
        )
        return message

    def _message_by_id(self, message_id: uuid.UUID) -> TicketMessage:
        for message in self.messages:
            if message.id == message_id:
                return message
        raise TicketMessageNotFoundError("message does not belong to the ticket")

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
