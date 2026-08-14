from typing import TypeVar

from fastapi import APIRouter, HTTPException, status

from app.models import User
from app.repository import UserAuditLogRepositoryDI, UserRepositoryDI
from app.schemas import PasswordChange, UserAuditLogResponse, UserId, UserResponse
from app.security import AdminUser, CurrentUser, hash_password, verify_password

T = TypeVar("T")

router = APIRouter(prefix="/users", tags=["users"])


@router.get("/", response_model=list[UserResponse])
async def list_users(
    _admin: AdminUser,
    repository: UserRepositoryDI,
) -> list[UserResponse]:
    return await repository.get_all_users()


@router.get("/audit", response_model=list[UserAuditLogResponse])
async def list_all_audit_logs(
    _admin: AdminUser,
    repository: UserAuditLogRepositoryDI,
) -> list[UserAuditLogResponse]:
    return await repository.get_all_audit_logs()


@router.get("/me", response_model=UserResponse)
async def read_current_user(current_user: CurrentUser) -> CurrentUser:
    return current_user


@router.get("/me/audit", response_model=list[UserAuditLogResponse])
async def read_own_audit_logs(
    current_user: CurrentUser,
    repository: UserAuditLogRepositoryDI,
) -> list[UserAuditLogResponse]:
    return await repository.get_audit_logs_by_user(current_user.id)


@router.patch("/me/password", response_model=UserResponse)
async def update_password(
    request: PasswordChange,
    current_user: CurrentUser,
    repository: UserRepositoryDI,
) -> User | None:
    if not verify_password(request.old_password, current_user.password_hash):
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Текущий пароль указан неверно",
        )

    return await repository.update_user_password(
        current_user.id,
        hash_password(request.new_password),
    )


@router.patch("/{user_id}/activate", response_model=UserResponse)
async def activate_user(
    admin: AdminUser,
    user_id: UserId,
    repository: UserRepositoryDI,
) -> User:
    return ensure_user_exists(await repository.set_active_user(user_id, True))


@router.patch("/{user_id}/deactivate", response_model=UserResponse)
async def deactivate_user(
    admin: AdminUser,
    user_id: UserId,
    repository: UserRepositoryDI,
) -> User:
    if user_id == admin.id:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Нельзя деактивировать собственную учетную запись",
        )

    return ensure_user_exists(await repository.set_active_user(user_id, False))


@router.get("/{user_id}/audit", response_model=list[UserAuditLogResponse])
async def read_user_audit_logs(
    _admin: AdminUser,
    user_id: UserId,
    repository: UserAuditLogRepositoryDI,
    user_repository: UserRepositoryDI,
) -> list[UserAuditLogResponse]:
    ensure_user_exists(await user_repository.get_user_by_id(user_id))
    return await repository.get_audit_logs_by_user(user_id)


def ensure_user_exists(entity: T | None) -> T:
    if not entity:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Пользователь не найден",
        )
    return entity
