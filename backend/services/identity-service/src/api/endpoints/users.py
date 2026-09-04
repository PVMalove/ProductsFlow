from typing import Annotated

from fastapi import APIRouter, Depends
from kernel_domain.result import Result
from kernel_platform.http.envelope import ApiResponse
from kernel_platform.http.errors import ApiError, status_code_for_error_type
from kernel_platform.http.match import match_result

from api.dependencies import (
    ActivateUserDI,
    ChangePasswordDI,
    DeactivateUserDI,
    DeleteAccountDI,
    GetCurrentUserDI,
    ListUsersDI,
    UserAuditDI,
)
from api.schemas import (
    PasswordChange,
    UserActivateRequest,
    UserDeactivateRequest,
    UserGlobalAuditRequest,
    UserListRequest,
    UserTargetAuditRequest,
)
from api.security import AdminActor, RequiredActor
from application.commands.delete_account import DeleteAccountCommand
from application.ports import UserAuditEntry, UserAuditPage
from application.queries import GetCurrentUserQuery, GetUserAuditQuery
from contracts.user import UserView
from domain.value_objects.user_id import UserId

router = APIRouter(prefix="/api/v1/users", tags=["users"])


def _unwrap[T](result: Result[T]) -> T:
    """Формы ответа, несущие больше одного `T` под `data`/`meta` (union
    `User*` vs list, кастомная offset-пагинация) не проходят через
    `match_result`/`match_page` — здесь сохраняется та же трансляция ошибок."""
    if result.is_err:
        error = result.error
        raise ApiError(
            status_code=status_code_for_error_type(error.type),
            code=error.code,
            message=error.description,
        )
    return result.value


@router.get("/me", response_model=ApiResponse[UserView])
async def read_current_user(
    actor: RequiredActor, handler: GetCurrentUserDI
) -> ApiResponse[UserView]:
    result = await handler.execute(GetCurrentUserQuery(user_id=UserId.create(actor.id)))
    return match_result(result)


@router.delete("/me", response_model=ApiResponse[None])
async def delete_own_account(
    actor: RequiredActor, handler: DeleteAccountDI
) -> ApiResponse[None]:
    result: Result[None] = await handler.execute(
        DeleteAccountCommand(user_id=UserId.create(actor.id))
    )
    return match_result(result)


@router.patch("/me/password", response_model=ApiResponse[UserView])
async def change_own_password(
    request: PasswordChange, actor: RequiredActor, handler: ChangePasswordDI
) -> ApiResponse[UserView]:
    command = request.to_command(actor=actor)
    result: Result[UserView] = await handler.execute(command)
    return match_result(result)


@router.get("/me/audit", response_model=ApiResponse[list[UserAuditEntry]])
async def read_own_audit_logs(
    actor: RequiredActor, handler: UserAuditDI
) -> ApiResponse[list[UserAuditEntry]]:
    entries = _unwrap(
        await handler.execute(GetUserAuditQuery(user_id=UserId.create(actor.id)))
    )
    assert isinstance(entries, list)
    return ApiResponse(data=entries)


@router.get("/audit", response_model=ApiResponse[list[UserAuditEntry]])
async def list_all_audit_logs(
    request: Annotated[UserGlobalAuditRequest, Depends()],
    _admin: AdminActor,
    handler: UserAuditDI,
) -> ApiResponse[list[UserAuditEntry]]:
    page = _unwrap(await handler.execute(request.to_query()))
    assert isinstance(page, UserAuditPage)
    return ApiResponse(
        data=page.items,
        meta={
            "page_index": page.page_index,
            "page_size": page.page_size,
            "total": page.total,
            "total_pages": page.total_pages,
        },
    )


@router.get("/", response_model=ApiResponse[list[UserView]])
async def list_users(
    request: Annotated[UserListRequest, Depends()],
    _admin: AdminActor,
    handler: ListUsersDI,
) -> ApiResponse[list[UserView]]:
    page = await handler.execute(request.to_query())
    return ApiResponse(
        data=[UserView.from_user(item) for item in page.items],
        meta={
            "next_cursor": page.page_info.next_cursor,
            "prev_cursor": page.page_info.prev_cursor,
            "has_more": page.page_info.has_more,
            "has_prev": page.page_info.has_prev,
        },
    )


@router.patch("/{user_id}/activate", response_model=ApiResponse[UserView])
async def activate_user(
    request: Annotated[UserActivateRequest, Depends()],
    _admin: AdminActor,
    handler: ActivateUserDI,
) -> ApiResponse[UserView]:
    command = request.to_command()
    result: Result[UserView] = await handler.execute(command)
    return match_result(result)


@router.patch("/{user_id}/deactivate", response_model=ApiResponse[UserView])
async def deactivate_user(
    request: Annotated[UserDeactivateRequest, Depends()],
    admin: AdminActor,
    handler: DeactivateUserDI,
) -> ApiResponse[UserView]:
    command = request.to_command(actor=admin)
    result: Result[UserView] = await handler.execute(command)
    return match_result(result)


@router.get("/{user_id}/audit", response_model=ApiResponse[list[UserAuditEntry]])
async def read_user_audit_logs(
    request: Annotated[UserTargetAuditRequest, Depends()],
    _admin: AdminActor,
    handler: UserAuditDI,
) -> ApiResponse[list[UserAuditEntry]]:
    entries = _unwrap(await handler.execute(request.to_query()))
    assert isinstance(entries, list)
    return ApiResponse(data=entries)
