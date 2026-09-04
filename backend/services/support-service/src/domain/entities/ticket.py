import uuid
from datetime import datetime
from typing import cast

from kernel_domain import PRIVATE_MARKER
from kernel_domain.entity import Entity
from kernel_domain.errors import Error, ErrorType
from kernel_domain.result import Result

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
    """Поднимается, когда обычная мутация нацелена на терминальный тикет."""


class InvalidStatusTransitionError(ValueError):
    """Поднимается, когда статус пропускает шаг или разворачивает обычный
    жизненный цикл."""


class TicketMessageNotFoundError(LookupError):
    """Поднимается, когда сообщение не принадлежит тикету."""


class TicketMessageImmutableError(ValueError):
    """Поднимается при попытке изменить системное сообщение."""


class TicketMessageAlreadyDeletedError(ValueError):
    """Поднимается при повторной мутации уже удалённого сообщения."""


_NEXT_STATUS = {
    TicketStatus.OPEN: TicketStatus.IN_PROGRESS,
    TicketStatus.IN_PROGRESS: TicketStatus.RESOLVED,
    TicketStatus.RESOLVED: TicketStatus.CLOSED,
}


def _ticket_closed_error(description: str) -> Error:
    return Error(code="ticket_closed", description=description, type=ErrorType.CONFLICT)


def _invalid_status_transition_error(description: str) -> Error:
    return Error(
        code="invalid_status_transition",
        description=description,
        type=ErrorType.CONFLICT,
    )


def _message_not_found_error(description: str) -> Error:
    return Error(
        code="message_not_found", description=description, type=ErrorType.NOT_FOUND
    )


class Ticket(Entity[TicketId]):
    """Агрегат Тикета поддержки (issue #252, #253). Дочерние `TicketMessage`
    мутируются через собственные `edit()`/`delete()` — `Ticket` пробрасывает
    их `Result.fail` дальше как свой собственный. Мутирующие методы
    (`add_message`, `change_status`, `edit_message`, `delete_message`,
    `anonymize_deleted_user`) не бросают исключений на бизнес-условиях,
    возвращают `Result`; трансляцию обратно в типизированные исключения
    делает `TicketRepository` на границе с БД.

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
    ) -> Result["Ticket"]:
        try:
            validate_plaintext(subject, field_name="subject", maximum=200)
        except ValueError as exc:
            return Result[Ticket].fail(
                Error(
                    code="invalid_subject",
                    description=str(exc),
                    type=ErrorType.VALIDATION,
                )
            )

        ticket_id = TicketId.new_id()
        try:
            message = TicketMessage.create(
                id=uuid.uuid4(),
                ticket_id=ticket_id,
                author_id=author_id,
                body=first_message,
            )
        except ValueError as exc:
            return Result[Ticket].fail(
                Error(
                    code="invalid_first_message",
                    description=str(exc),
                    type=ErrorType.VALIDATION,
                )
            )
        ticket = cls(
            PRIVATE_MARKER,
            ticket_id,
            author_id=author_id,
            subject=subject,
            status=TicketStatus.OPEN,
            messages=[message],
        )
        ticket.add_domain_event(TicketCreated(ticket_id=ticket_id, author_id=author_id))
        return Result[Ticket].ok(ticket)

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
            PRIVATE_MARKER,
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
    ) -> Result[TicketMessage]:
        if self.status is TicketStatus.CLOSED:
            return Result[TicketMessage].fail(
                _ticket_closed_error("closed tickets cannot receive messages")
            )

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
        return Result[TicketMessage].ok(message)

    def change_status(
        self, status: TicketStatus, *, actor_category: str
    ) -> Result[None]:
        return self._change_status(status, actor_category=actor_category)

    def anonymize_deleted_user(self, user_id: uuid.UUID) -> Result[bool]:
        """Удаляет личность удалённого пользователя и закрывает его активный тикет.

        Событие удаления фиксируется application inbox, поэтому эта операция
        над агрегатом намеренно безопасна к повторному вызову: уже
        анонимизированный тикет не может получить ещё одно системное
        сообщение.
        """
        owns_ticket = self.author_id == user_id
        if owns_ticket:
            self.author_id = None

        for message in self.messages:
            if message.author_id == user_id:
                object.__setattr__(message, "author_id", None)

        if not owns_ticket or self.status is TicketStatus.CLOSED:
            return Result[bool].ok(owns_ticket)

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
        return Result[bool].ok(True)

    def edit_message(
        self,
        *,
        message_id: uuid.UUID,
        author_id: uuid.UUID,
        body: str,
        actor_category: str,
    ) -> Result[TicketMessage]:
        if self.status is TicketStatus.CLOSED:
            return Result[TicketMessage].fail(
                _ticket_closed_error("closed tickets cannot edit messages")
            )
        message = self._message_by_id(message_id)
        if message is None:
            return Result[TicketMessage].fail(
                _message_not_found_error("message does not belong to the ticket")
            )
        if message.author_id != author_id:
            return Result[TicketMessage].fail(
                _message_not_found_error("message is owned by another author")
            )

        result = message.edit(body)
        if result.is_err:
            return Result[TicketMessage].fail(result.error)

        self.add_domain_event(
            TicketMessageEdited(
                ticket_id=self.id,
                message_id=message.id,
                actor_category=actor_category,
            )
        )
        return Result[TicketMessage].ok(message)

    def delete_message(
        self,
        *,
        message_id: uuid.UUID,
        actor_id: uuid.UUID,
        actor_category: str,
    ) -> Result[TicketMessage]:
        if self.status is TicketStatus.CLOSED and actor_category != "admin":
            return Result[TicketMessage].fail(
                _ticket_closed_error("closed tickets cannot delete messages")
            )
        message = self._message_by_id(message_id)
        if message is None:
            return Result[TicketMessage].fail(
                _message_not_found_error("message does not belong to the ticket")
            )
        if actor_category != "admin" and message.author_id != actor_id:
            return Result[TicketMessage].fail(
                _message_not_found_error("message is owned by another author")
            )

        result = message.delete()
        if result.is_err:
            return Result[TicketMessage].fail(result.error)

        self.add_domain_event(
            TicketMessageDeleted(
                ticket_id=self.id,
                message_id=message.id,
                actor_category=actor_category,
            )
        )
        return Result[TicketMessage].ok(message)

    def _message_by_id(self, message_id: uuid.UUID) -> TicketMessage | None:
        for message in self.messages:
            if message.id == message_id:
                return message
        return None

    def _change_status(
        self,
        status: TicketStatus,
        *,
        actor_category: str,
        allow_reopen: bool = False,
    ) -> Result[None]:
        if self.status is TicketStatus.CLOSED:
            return Result[None].fail(
                _ticket_closed_error("closed tickets have a terminal status")
            )
        if not allow_reopen and _NEXT_STATUS.get(self.status) is not status:
            return Result[None].fail(
                _invalid_status_transition_error(
                    f"cannot change status from {self.status} to {status}"
                )
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
        return Result[None].ok(None)
