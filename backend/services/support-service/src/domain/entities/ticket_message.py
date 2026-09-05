import uuid
from dataclasses import dataclass
from datetime import UTC, datetime

from kernel_domain.errors import Error
from kernel_domain.result import Result

from domain.errors import SupportErrors
from domain.value_objects import PRIVATE_MARKER
from domain.value_objects.ticket_id import TicketId

DELETED_MESSAGE_MARKER = "[Сообщение удалено]"

_MISSING = object()


@dataclass(frozen=True, slots=True)
class TicketMessage:
    """Дочерняя сущность агрегата `Ticket`. Не эмитит собственных доменных
    событий — `Ticket` остаётся единственным источником событий агрегата и
    сам решает, какое событие добавить после успешной мутации `edit()`/
    `delete()`.

    Конструктор вызывается только через `create()` (новое сообщение) или
    `reconstitute()` (гидратация из БД) — прямой вызов `TicketMessage(...)`
    бросает `RuntimeError`."""

    id: uuid.UUID
    ticket_id: TicketId
    author_id: uuid.UUID | None
    body: str
    created_at: datetime
    is_system: bool
    is_deleted: bool

    def __init__(
        self,
        marker: object = _MISSING,
        *,
        id: uuid.UUID,
        ticket_id: TicketId,
        author_id: uuid.UUID | None,
        body: str,
        created_at: datetime | None = None,
        is_system: bool = False,
        is_deleted: bool = False,
    ) -> None:
        if marker is not PRIVATE_MARKER:
            raise RuntimeError(
                "TicketMessage instances must be created through "
                "TicketMessage.create()/reconstitute()"
            )
        object.__setattr__(self, "id", id)
        object.__setattr__(self, "ticket_id", ticket_id)
        object.__setattr__(self, "author_id", author_id)
        object.__setattr__(self, "body", body)
        object.__setattr__(self, "created_at", created_at or datetime.now(UTC))
        object.__setattr__(self, "is_system", is_system)
        object.__setattr__(self, "is_deleted", is_deleted)

    @classmethod
    def create(
        cls,
        *,
        id: uuid.UUID,
        ticket_id: TicketId,
        author_id: uuid.UUID | None,
        body: str,
        is_system: bool = False,
    ) -> Result["TicketMessage"]:
        body_result = validate_plaintext(
            body, error=SupportErrors.invalid_body(), maximum=10_000
        )
        if body_result.is_err:
            return Result[TicketMessage].fail(body_result.error)
        return Result[TicketMessage].ok(
            cls(
                PRIVATE_MARKER,
                id=id,
                ticket_id=ticket_id,
                author_id=author_id,
                body=body_result.value,
                is_system=is_system,
            )
        )

    @classmethod
    def reconstitute(
        cls,
        *,
        id: uuid.UUID,
        ticket_id: TicketId,
        author_id: uuid.UUID | None,
        body: str,
        created_at: datetime,
        is_system: bool,
        is_deleted: bool,
    ) -> "TicketMessage":
        return cls(
            PRIVATE_MARKER,
            id=id,
            ticket_id=ticket_id,
            author_id=author_id,
            body=body,
            created_at=created_at,
            is_system=is_system,
            is_deleted=is_deleted,
        )

    def edit(self, body: str) -> Result[None]:
        error = self._immutability_error()
        if error is not None:
            return Result[None].fail(error)

        body_result = validate_plaintext(
            body, error=SupportErrors.invalid_body(), maximum=10_000
        )
        if body_result.is_err:
            return Result[None].fail(body_result.error)

        object.__setattr__(self, "body", body_result.value)
        return Result[None].ok(None)

    def delete(self) -> Result[None]:
        error = self._immutability_error()
        if error is not None:
            return Result[None].fail(error)

        object.__setattr__(self, "body", DELETED_MESSAGE_MARKER)
        object.__setattr__(self, "is_deleted", True)
        return Result[None].ok(None)

    def _immutability_error(self) -> Error | None:
        if self.is_system:
            return SupportErrors.message_immutable()
        if self.is_deleted:
            return SupportErrors.message_already_deleted()
        return None


def validate_plaintext(value: str, *, error: Error, maximum: int) -> Result[str]:
    trimmed = value.strip()
    if not trimmed or len(trimmed) > maximum:
        return Result[str].fail(error)
    return Result[str].ok(trimmed)
