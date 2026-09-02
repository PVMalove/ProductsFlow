from typing import Annotated
from uuid import UUID

from fastapi import APIRouter, HTTPException, Query, status
from kernel_platform.pagination import (
    DEFAULT_PAGE_LIMIT,
    MAX_PAGE_LIMIT,
    InvalidCursorError,
    decode_cursor,
)

from api.dependencies import (
    ActivateUserDI,
    ChangePasswordDI,
    DeactivateUserDI,
    ListUsersDI,
    UserAuditDI,
    UserAuditReaderDI,
    UserQueryRepositoryDI,
)
from api.errors import raise_command_error
from api.schemas import (
    PasswordChange,
    UserAuditLogPageResponse,
    UserAuditLogResponse,
    UserListResponse,
    UserResponse,
    audit_entry_response,
    audit_page_response,
    user_list_response,
    user_response,
)
from api.security import AdminUser, CurrentUser
from application.commands import (
    ActivateUserCommand,
    ChangePasswordCommand,
    DeactivateUserCommand,
)
from application.ports import UserAuditPage
from application.queries import GetUserAuditQuery, ListUsersQuery
from domain.user_id import UserId

router = APIRouter(prefix="/api/v1/users", tags=["users"])


@router.get("/me", response_model=UserResponse)
async def read_current_user(current_user: CurrentUser) -> UserResponse:
    return user_response(current_user)


@router.patch("/me/password", response_model=UserResponse)
async def change_own_password(
    request: PasswordChange,
    current_user: CurrentUser,
    handler: ChangePasswordDI,
) -> UserResponse:
    result = await handler.execute(
        ChangePasswordCommand(
            user_id=current_user.id,
            old_password=request.old_password,
            new_password=request.new_password,
        )
    )
    if result.is_err:
        raise_command_error(result)
    return user_response(result.value)


@router.get("/me/audit", response_model=list[UserAuditLogResponse])
async def read_own_audit_logs(
    current_user: CurrentUser, handler: UserAuditDI
) -> list[UserAuditLogResponse]:
    result = await handler.execute(GetUserAuditQuery(user_id=current_user.id))
    if not isinstance(result, list):
        raise RuntimeError("Персональный audit вернул глобальную страницу")
    return [audit_entry_response(entry) for entry in result]


@router.get("/audit", response_model=UserAuditLogPageResponse)
async def list_all_audit_logs(
    _admin: AdminUser,
    handler: UserAuditDI,
    page_index: Annotated[int, Query(ge=1)] = 1,
    page_size: Annotated[int, Query(ge=1)] = 10,
) -> UserAuditLogPageResponse:
    result = await handler.execute(
        GetUserAuditQuery(page_index=page_index, page_size=page_size)
    )
    if not isinstance(result, UserAuditPage):
        raise RuntimeError("Глобальный audit вернул персональный список")
    return audit_page_response(result)


@router.get("/", response_model=UserListResponse)
async def list_users(
    _admin: AdminUser,
    handler: ListUsersDI,
    limit: Annotated[int, Query(ge=1, le=MAX_PAGE_LIMIT)] = DEFAULT_PAGE_LIMIT,
    after: str | None = None,
    before: str | None = None,
) -> UserListResponse:
    if after is not None and before is not None:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Нельзя одновременно указать after и before",
        )
    try:
        after_cursor = decode_cursor(after) if after is not None else None
        before_cursor = decode_cursor(before) if before is not None else None
    except InvalidCursorError as exc:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Некорректный курсор пагинации",
        ) from exc
    result = await handler.execute(
        ListUsersQuery(limit=limit, after=after_cursor, before=before_cursor)
    )
    return user_list_response(result)


@router.patch("/{user_id}/activate", response_model=UserResponse)
async def activate_user(
    user_id: UUID, _admin: AdminUser, handler: ActivateUserDI
) -> UserResponse:
    result = await handler.execute(ActivateUserCommand(UserId(user_id)))
    if result.is_err:
        raise_command_error(result)
    return user_response(result.value)


@router.patch("/{user_id}/deactivate", response_model=UserResponse)
async def deactivate_user(
    user_id: UUID, admin: AdminUser, handler: DeactivateUserDI
) -> UserResponse:
    result = await handler.execute(
        DeactivateUserCommand(target_user_id=UserId(user_id), actor_user_id=admin.id)
    )
    if result.is_err:
        raise_command_error(result)
    return user_response(result.value)


@router.get("/{user_id}/audit", response_model=list[UserAuditLogResponse])
async def read_user_audit_logs(
    user_id: UUID,
    _admin: AdminUser,
    user_query: UserQueryRepositoryDI,
    audit_reader: UserAuditReaderDI,
) -> list[UserAuditLogResponse]:
    target_id = UserId(user_id)
    if await user_query.get_by_id(target_id) is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Пользователь не найден",
        )
    entries = await audit_reader.get_by_user(target_id)
    return [audit_entry_response(entry) for entry in entries]
