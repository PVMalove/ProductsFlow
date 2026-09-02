import uuid
from dataclasses import dataclass, field
from datetime import UTC, datetime

DELETED_MESSAGE_MARKER = "[Сообщение удалено]"


@dataclass(frozen=True, slots=True)
class TicketMessage:
    id: uuid.UUID
    ticket_id: uuid.UUID
    author_id: uuid.UUID | None
    body: str
    created_at: datetime = field(default_factory=lambda: datetime.now(UTC))
    is_system: bool = False
    is_deleted: bool = False

    def __post_init__(self) -> None:
        if not isinstance(self.id, uuid.UUID) or not isinstance(
            self.ticket_id, uuid.UUID
        ):
            raise ValueError("message identifiers must be UUIDs")
        if self.author_id is not None and not isinstance(self.author_id, uuid.UUID):
            raise ValueError("message author must be a UUID")
        object.__setattr__(
            self,
            "body",
            validate_plaintext(self.body, field_name="body", maximum=10_000),
        )


def validate_plaintext(value: str, *, field_name: str, maximum: int) -> str:
    value = value.strip()
    if not value or len(value) > maximum:
        raise ValueError(f"{field_name} must contain 1-{maximum} characters")
    return value
