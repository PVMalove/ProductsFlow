import uuid
from typing import Any

from fastapi import Query
from kernel_platform.security import Actor, ActorRole
from pydantic import BaseModel, Field, field_validator

from application.commands import (
    AddTicketMessageCommand,
    ChangeTicketStatusCommand,
    CreateTicketCommand,
    DeleteTicketMessageCommand,
    EditTicketMessageCommand,
)
from application.errors import (
    TicketListCursorConflictError,
    TicketListInvalidCursorError,
)
from application.pagination import (
    DEFAULT_PAGE_LIMIT,
    MAX_PAGE_LIMIT,
    InvalidCursorError,
    decode_cursor,
)
from application.queries import (
    GetTicketDetailQuery,
    ListAdminTicketsQuery,
    ListTicketsQuery,
)
from domain.ticket_status import TicketStatus
from domain.value_objects.ticket_id import TicketId


def _is_admin(actor: Actor) -> bool:
    return actor.role is ActorRole.ADMIN


def _decode_cursors(after: str | None, before: str | None) -> tuple[Any, Any]:
    if after is not None and before is not None:
        raise TicketListCursorConflictError
    try:
        after_cursor = decode_cursor(after) if after is not None else None
        before_cursor = decode_cursor(before) if before is not None else None
    except InvalidCursorError as exc:
        raise TicketListInvalidCursorError from exc
    return after_cursor, before_cursor


class TicketCreateRequest(BaseModel):
    subject: str = Field(min_length=1, max_length=200)
    first_message: str = Field(min_length=1, max_length=10_000)

    @field_validator("subject", "first_message", mode="before")
    @classmethod
    def trim_plaintext(cls, value: Any) -> Any:
        return value.strip() if isinstance(value, str) else value

    def to_command(self, *, actor: Actor) -> CreateTicketCommand:
        return CreateTicketCommand(
            author_id=actor.id, subject=self.subject, first_message=self.first_message
        )


class TicketListRequest(BaseModel):
    """Query-bound — the caller's own cursor-paginated tickets."""

    limit: int = Query(default=DEFAULT_PAGE_LIMIT, ge=1, le=MAX_PAGE_LIMIT)
    after: str | None = Query(default=None)
    before: str | None = Query(default=None)

    def to_query(self, *, actor: Actor) -> ListTicketsQuery:
        after_cursor, before_cursor = _decode_cursors(self.after, self.before)
        return ListTicketsQuery(
            author_id=actor.id,
            limit=self.limit,
            after=after_cursor,
            before=before_cursor,
        )


class AdminTicketListRequest(BaseModel):
    """Query-bound — every ticket, cursor-paginated."""

    limit: int = Query(default=DEFAULT_PAGE_LIMIT, ge=1, le=MAX_PAGE_LIMIT)
    after: str | None = Query(default=None)
    before: str | None = Query(default=None)

    def to_query(self, *, actor: Actor) -> ListAdminTicketsQuery:
        after_cursor, before_cursor = _decode_cursors(self.after, self.before)
        return ListAdminTicketsQuery(
            limit=self.limit,
            is_admin=_is_admin(actor),
            after=after_cursor,
            before=before_cursor,
        )


class TicketDetailRequest(BaseModel):
    """Path- and query-bound — `ticket_id` from the URL, pagination for its
    first page of messages from the query string."""

    ticket_id: uuid.UUID
    limit: int = Query(default=DEFAULT_PAGE_LIMIT, ge=1, le=MAX_PAGE_LIMIT)
    after: str | None = Query(default=None)
    before: str | None = Query(default=None)

    def to_query(self, *, actor: Actor) -> GetTicketDetailQuery:
        after_cursor, before_cursor = _decode_cursors(self.after, self.before)
        return GetTicketDetailQuery(
            ticket_id=TicketId.create(self.ticket_id),
            actor_id=actor.id,
            is_admin=_is_admin(actor),
            limit=self.limit,
            after=after_cursor,
            before=before_cursor,
        )


class AdminTicketDetailRequest(BaseModel):
    """Path- and query-bound — same shape as `TicketDetailRequest`, but its
    query forces the admin-only gate (`GET /tickets/admin/{ticket_id}`)."""

    ticket_id: uuid.UUID
    limit: int = Query(default=DEFAULT_PAGE_LIMIT, ge=1, le=MAX_PAGE_LIMIT)
    after: str | None = Query(default=None)
    before: str | None = Query(default=None)

    def to_query(self, *, actor: Actor) -> GetTicketDetailQuery:
        after_cursor, before_cursor = _decode_cursors(self.after, self.before)
        return GetTicketDetailQuery(
            ticket_id=TicketId.create(self.ticket_id),
            actor_id=actor.id,
            is_admin=_is_admin(actor),
            limit=self.limit,
            after=after_cursor,
            before=before_cursor,
            require_admin=True,
        )


class TicketMessageCreateRequest(BaseModel):
    body: str = Field(min_length=1, max_length=10_000)

    @field_validator("body", mode="before")
    @classmethod
    def trim_plaintext(cls, value: Any) -> Any:
        return value.strip() if isinstance(value, str) else value

    def to_command(
        self, *, ticket_id: uuid.UUID, actor: Actor
    ) -> AddTicketMessageCommand:
        return AddTicketMessageCommand(
            ticket_id=TicketId.create(ticket_id),
            actor_id=actor.id,
            body=self.body,
            is_admin=_is_admin(actor),
        )

    def to_edit_command(
        self, *, ticket_id: uuid.UUID, message_id: uuid.UUID, actor: Actor
    ) -> EditTicketMessageCommand:
        return EditTicketMessageCommand(
            ticket_id=TicketId.create(ticket_id),
            message_id=message_id,
            actor_id=actor.id,
            body=self.body,
            is_admin=_is_admin(actor),
        )


class TicketStatusChangeRequest(BaseModel):
    status: TicketStatus

    def to_command(
        self, *, ticket_id: uuid.UUID, actor: Actor
    ) -> ChangeTicketStatusCommand:
        return ChangeTicketStatusCommand(
            ticket_id=TicketId.create(ticket_id),
            actor_id=actor.id,
            status=self.status,
            is_admin=_is_admin(actor),
        )


class TicketMessageDeleteRequest(BaseModel):
    """Path-bound — without a JSON body, ids come from the URL."""

    ticket_id: uuid.UUID
    message_id: uuid.UUID

    def to_command(self, *, actor: Actor) -> DeleteTicketMessageCommand:
        return DeleteTicketMessageCommand(
            ticket_id=TicketId.create(self.ticket_id),
            message_id=self.message_id,
            actor_id=actor.id,
            is_admin=_is_admin(actor),
        )
