from typing import Annotated

from fastapi import APIRouter, Depends
from kernel_domain.result import Result
from kernel_platform.http.envelope import ApiResponse
from kernel_platform.http.match import (
    match_offset_page,
    match_page,
    match_result,
    unwrap_result,
)
from kernel_platform.pagination import Page

from api.http.dependencies import (
    ActivateUserDI,
    ChangePasswordDI,
    DeactivateUserDI,
    DeleteAccountDI,
    GetCurrentUserDI,
    GlobalAuditDI,
    ListUsersDI,
    PersonalAuditDI,
)
from api.http.schemas import (
    PasswordChange,
    UserActivateRequest,
    UserDeactivateRequest,
    UserGlobalAuditRequest,
    UserListRequest,
    UserTargetAuditRequest,
)
from api.http.security import AdminActor, RequiredActor
from application.commands import (
    ActivateUserCommand,
    ChangePasswordCommand,
    DeactivateUserCommand,
    DeleteAccountCommand,
)
from application.ports import UserAuditEntry
from application.queries import (
    GetCurrentUserQuery,
    GetGlobalAuditQuery,
    GetPersonalAuditQuery,
    ListUsersQuery,
)
from contracts.user import UserView
from domain.value_objects.user_id import UserId

router = APIRouter(prefix="/api/v1/users", tags=["users"])


@router.get("/me", response_model=ApiResponse[UserView])
async def read_current_user(
    actor: RequiredActor, handler: GetCurrentUserDI
) -> ApiResponse[UserView]:
    query: GetCurrentUserQuery = GetCurrentUserQuery(user_id=UserId.create(actor.id))
    result: Result[UserView] = await handler.execute(query)
    return match_result(result)


@router.delete("/me", response_model=ApiResponse[None])
async def delete_own_account(
    actor: RequiredActor, handler: DeleteAccountDI
) -> ApiResponse[None]:
    command: DeleteAccountCommand = DeleteAccountCommand(
        user_id=UserId.create(actor.id)
    )
    result: Result[None] = await handler.execute(command)
    return match_result(result)


@router.patch("/me/password", response_model=ApiResponse[UserView])
async def change_own_password(
    request: PasswordChange, actor: RequiredActor, handler: ChangePasswordDI
) -> ApiResponse[UserView]:
    command: ChangePasswordCommand = request.to_command(actor=actor)
    result: Result[UserView] = await handler.execute(command)
    return match_result(result)


@router.get("/me/audit", response_model=ApiResponse[list[UserAuditEntry]])
async def read_own_audit_logs(
    actor: RequiredActor, handler: PersonalAuditDI
) -> ApiResponse[list[UserAuditEntry]]:
    query: GetPersonalAuditQuery = GetPersonalAuditQuery(
        user_id=UserId.create(actor.id)
    )
    result = await handler.execute(query)
    return match_result(result)


@router.get("/audit", response_model=ApiResponse[list[UserAuditEntry]])
async def list_all_audit_logs(
    request: Annotated[UserGlobalAuditRequest, Depends()],
    _admin: AdminActor,
    handler: GlobalAuditDI,
) -> ApiResponse[list[UserAuditEntry]]:
    query: GetGlobalAuditQuery = request.to_query()
    result = await handler.execute(query)
    return match_offset_page(result)


@router.get("/", response_model=ApiResponse[list[UserView]])
async def list_users(
    request: Annotated[UserListRequest, Depends()],
    _admin: AdminActor,
    handler: ListUsersDI,
) -> ApiResponse[list[UserView]]:
    query: ListUsersQuery = request.to_query()
    page = unwrap_result(await handler.execute(query))
    view_page = Page[UserView](
        items=[UserView.from_user(item) for item in page.items],
        page_info=page.page_info,
    )
    return match_page(Result.ok(view_page))


@router.patch("/{user_id}/activate", response_model=ApiResponse[UserView])
async def activate_user(
    request: Annotated[UserActivateRequest, Depends()],
    _admin: AdminActor,
    handler: ActivateUserDI,
) -> ApiResponse[UserView]:
    command: ActivateUserCommand = request.to_command()
    result: Result[UserView] = await handler.execute(command)
    return match_result(result)


@router.patch("/{user_id}/deactivate", response_model=ApiResponse[UserView])
async def deactivate_user(
    request: Annotated[UserDeactivateRequest, Depends()],
    admin: AdminActor,
    handler: DeactivateUserDI,
) -> ApiResponse[UserView]:
    command: DeactivateUserCommand = request.to_command(actor=admin)
    result: Result[UserView] = await handler.execute(command)
    return match_result(result)


@router.get("/{user_id}/audit", response_model=ApiResponse[list[UserAuditEntry]])
async def read_user_audit_logs(
    request: Annotated[UserTargetAuditRequest, Depends()],
    _admin: AdminActor,
    handler: PersonalAuditDI,
) -> ApiResponse[list[UserAuditEntry]]:
    query: GetPersonalAuditQuery = request.to_query()
    result = await handler.execute(query)
    return match_result(result)
