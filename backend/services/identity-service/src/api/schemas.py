from datetime import datetime
from uuid import UUID

from pydantic import BaseModel, ConfigDict, field_validator

from application.ports import (
    UserAuditAction,
    UserAuditEntry,
    UserAuditPage,
    UserPage,
    UserReadModel,
)
from domain.email import Email
from domain.role import Role
from domain.user import User


class UserCreate(BaseModel):
    email: str
    password: str

    @field_validator("email")
    @classmethod
    def validate_email(cls, value: str) -> str:
        Email(value)
        return value


class UserResponse(BaseModel):
    id: UUID
    email: str
    role: Role
    is_active: bool

    model_config = ConfigDict(from_attributes=True)


class TokenResponse(BaseModel):
    access_token: str
    token_type: str = "bearer"


class PasswordChange(BaseModel):
    old_password: str
    new_password: str


class PageInfoResponse(BaseModel):
    next_cursor: str | None
    prev_cursor: str | None
    has_more: bool
    has_prev: bool


class UserListResponse(BaseModel):
    items: list[UserResponse]
    page_info: PageInfoResponse


class UserAuditLogResponse(BaseModel):
    id: int
    user_id: UUID
    actor_user_id: UUID
    action: UserAuditAction
    description: str
    created_at: datetime


class UserAuditLogPageResponse(BaseModel):
    items: list[UserAuditLogResponse]
    page_index: int
    page_size: int
    total: int
    total_pages: int


def user_response(user: User | UserReadModel) -> UserResponse:
    return UserResponse(
        id=user.id.value,
        email=user.email.value,
        role=user.role,
        is_active=user.is_active,
    )


read_model_response = user_response


def user_list_response(page: UserPage) -> UserListResponse:
    return UserListResponse(
        items=[read_model_response(item) for item in page.items],
        page_info=PageInfoResponse(
            next_cursor=page.page_info.next_cursor,
            prev_cursor=page.page_info.prev_cursor,
            has_more=page.page_info.has_more,
            has_prev=page.page_info.has_prev,
        ),
    )


def audit_entry_response(entry: UserAuditEntry) -> UserAuditLogResponse:
    return UserAuditLogResponse(
        id=entry.id,
        user_id=entry.user_id.value,
        actor_user_id=entry.actor_user_id.value,
        action=entry.action,
        description=entry.description,
        created_at=entry.created_at,
    )


def audit_page_response(page: UserAuditPage) -> UserAuditLogPageResponse:
    return UserAuditLogPageResponse(
        items=[audit_entry_response(item) for item in page.items],
        page_index=page.page_index,
        page_size=page.page_size,
        total=page.total,
        total_pages=page.total_pages,
    )


__all__ = [
    "PasswordChange",
    "TokenResponse",
    "UserAuditLogPageResponse",
    "UserAuditLogResponse",
    "UserCreate",
    "UserListResponse",
    "UserResponse",
    "audit_entry_response",
    "audit_page_response",
    "read_model_response",
    "user_list_response",
    "user_response",
]
