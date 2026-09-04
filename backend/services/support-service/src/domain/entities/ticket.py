import uuid
from datetime import datetime
from typing import cast

from kernel_domain import _PRIVATE_MARKER
from kernel_domain.entity import Entity

from domain.entities.ticket_message import TicketMessage, validate_plaintext
from domain.events.ticket_domain_event import (
    TicketCreated,
    TicketMessageAdded,
    TicketMessageDeleted,
    TicketMessageEdited,
    TicketStatusChanged,
)
from domain.ticket_status import TicketStatus
from domain.value_objects.ticket_id import TicketId

USER_DELETED_MESSAGE = "[Пользователь удалён]"

_MISSING = object()


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


_NEXT_STATUS = {
    TicketStatus.OPEN: TicketStatus.IN_PROGRESS,
    TicketStatus.IN_PROGRESS: TicketStatus.RESOLVED,
    TicketStatus.RESOLVED: TicketStatus.CLOSED,
}


class Ticket(Entity[TicketId]):
    """Агрегат Тикета поддержки (issue #252). Дочерние `TicketMessage`
    мутируются через собственные `edit()`/`delete()` — `Ticket` разворачивает
    их `Result.fail` в те же исключения, что бросал раньше напрямую.

    Конструктор вызывается только через `create()` (новый тикет) или
    `reconstitute()` (гидратация из БД) — маркер приватности проверяется
    централизованно в `Entity.__init__`."""

    def __init__(
        self,
        marker: object = _MISSING,
        id: TicketId = cast("TicketId", _MISSING),
        *,
        author_id: uuid.UUID | None,
        subject: str,
        status: TicketStatus = TicketStatus.OPEN,
        messages: list[TicketMessage] | None = None,
        created_at: datetime | None = None,
    ) -> None:
        super().__init__(marker, id=id)
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
        ticket_id = TicketId.new_id()
        message = TicketMessage.create(
            id=uuid.uuid4(),
            ticket_id=ticket_id,
            author_id=author_id,
            body=first_message,
        )
        ticket = cls(
            _PRIVATE_MARKER,
            ticket_id,
            author_id=author_id,
            subject=subject,
            status=TicketStatus.OPEN,
            messages=[message],
        )
        ticket.add_domain_event(TicketCreated(ticket_id=ticket_id, author_id=author_id))
        return ticket

    @classmethod
    def reconstitute(
        cls,
        id: TicketId,
        *,
        author_id: uuid.UUID | None,
        subject: str,
        status: TicketStatus,
        messages: list[TicketMessage],
        created_at: datetime,
    ) -> "Ticket":
        return cls(
            _PRIVATE_MARKER,
            id,
            author_id=author_id,
            subject=subject,
            status=status,
            messages=messages,
            created_at=created_at,
        )

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

        message = TicketMessage.create(
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
        system_message = TicketMessage.create(
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

        result = message.edit(body)
        if result.is_err:
            if result.error.code == "message_immutable":
                raise TicketMessageImmutableError("system messages cannot be edited")
            raise TicketMessageAlreadyDeletedError("deleted messages cannot be edited")

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

        result = message.delete()
        if result.is_err:
            if result.error.code == "message_immutable":
                raise TicketMessageImmutableError("system messages cannot be deleted")
            raise TicketMessageAlreadyDeletedError("message is already deleted")

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
