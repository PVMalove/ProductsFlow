from uuid import UUID

from fastapi import Query
from kernel_platform.pagination import (
    DEFAULT_PAGE_LIMIT,
    MAX_PAGE_LIMIT,
    InvalidCursorError,
    decode_cursor,
)
from kernel_platform.security import Actor
from pydantic import BaseModel

from application.commands import (
    ActivateUserCommand,
    ChangePasswordCommand,
    DeactivateUserCommand,
    RegisterUserCommand,
)
from application.errors import UserListCursorConflictError, UserListInvalidCursorError
from application.queries import GetUserAuditQuery, ListUsersQuery
from domain.value_objects.user_id import UserId


class UserCreate(BaseModel):
    email: str
    password: str

    def to_command(self) -> RegisterUserCommand:
        return RegisterUserCommand(email=self.email, password=self.password)


class TokenResponse(BaseModel):
    access_token: str
    token_type: str = "bearer"


class PasswordChange(BaseModel):
    old_password: str
    new_password: str

    def to_command(self, *, actor: Actor) -> ChangePasswordCommand:
        return ChangePasswordCommand(
            user_id=UserId.create(actor.id),
            old_password=self.old_password,
            new_password=self.new_password,
        )


class UserActivateRequest(BaseModel):
    """Path-bound — without a JSON body, `user_id` comes from the URL."""

    user_id: UUID

    def to_command(self) -> ActivateUserCommand:
        return ActivateUserCommand(target_user_id=UserId.create(self.user_id))


class UserDeactivateRequest(BaseModel):
    """Path-bound — without a JSON body, `user_id` comes from the URL."""

    user_id: UUID

    def to_command(self, *, actor: Actor) -> DeactivateUserCommand:
        return DeactivateUserCommand(
            target_user_id=UserId.create(self.user_id),
            actor_user_id=UserId.create(actor.id),
        )


class UserTargetAuditRequest(BaseModel):
    """Path-bound — without a JSON body, `user_id` comes from the URL."""

    user_id: UUID

    def to_query(self) -> GetUserAuditQuery:
        return GetUserAuditQuery(user_id=UserId.create(self.user_id))


class UserGlobalAuditRequest(BaseModel):
    """Query-bound — offset pagination for the global admin audit feed."""

    page_index: int = Query(default=1, ge=1)
    page_size: int = Query(default=DEFAULT_PAGE_LIMIT, ge=1, le=MAX_PAGE_LIMIT)

    def to_query(self) -> GetUserAuditQuery:
        return GetUserAuditQuery(page_index=self.page_index, page_size=self.page_size)


class UserListRequest(BaseModel):
    """Query-bound — `limit`/`after`/`before` come from the query string."""

    limit: int = Query(default=DEFAULT_PAGE_LIMIT, ge=1, le=MAX_PAGE_LIMIT)
    after: str | None = Query(default=None)
    before: str | None = Query(default=None)

    def to_query(self) -> ListUsersQuery:
        if self.after is not None and self.before is not None:
            raise UserListCursorConflictError
        try:
            after_cursor = decode_cursor(self.after) if self.after is not None else None
            before_cursor = (
                decode_cursor(self.before) if self.before is not None else None
            )
        except InvalidCursorError as exc:
            raise UserListInvalidCursorError from exc
        return ListUsersQuery(
            limit=self.limit, after=after_cursor, before=before_cursor
        )


__all__ = [
    "MAX_PAGE_LIMIT",
    "PasswordChange",
    "TokenResponse",
    "UserActivateRequest",
    "UserCreate",
    "UserDeactivateRequest",
    "UserGlobalAuditRequest",
    "UserListRequest",
    "UserTargetAuditRequest",
]
