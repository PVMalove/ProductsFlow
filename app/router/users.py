from fastapi import APIRouter, HTTPException, status

from app import audit
from app.db import Session
from app.models import AuditAction, User
from app.repository import AuditLogRepositoryDI, UserRepositoryDI
from app.schemas import AuditLogResponse, PasswordChange, UserId, UserResponse
from app.security import AdminUser, CurrentUser, hash_password, verify_password

router = APIRouter(prefix="/users", tags=["users"])


@router.get("/", response_model=list[UserResponse])
async def list_users(
    _admin: AdminUser,
    repository: UserRepositoryDI,
) -> list[UserResponse]:
    return await repository.get_all_users()


@router.get("/audit", response_model=list[AuditLogResponse])
async def list_all_audit_logs(
    _admin: AdminUser,
    repository: AuditLogRepositoryDI,
) -> list[AuditLogResponse]:
    return await repository.get_all_audit_logs()


@router.get("/me", response_model=UserResponse)
async def read_current_user(current_user: CurrentUser) -> CurrentUser:
    return current_user


@router.get("/me/audit", response_model=list[AuditLogResponse])
async def read_own_audit_logs(
    current_user: CurrentUser,
    repository: AuditLogRepositoryDI,
) -> list[AuditLogResponse]:
    return await repository.get_audit_logs_by_user(current_user.id)


@router.patch("/me/password", response_model=UserResponse)
async def update_password(
    request: PasswordChange,
    current_user: CurrentUser,
    session: Session,
    repository: UserRepositoryDI,
) -> User | None:
    if not verify_password(request.old_password, current_user.password_hash):
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Текущий пароль указан неверно",
        )

    user = await repository.update_user_password(
        current_user.id,
        hash_password(request.new_password),
    )

    await audit.record(
        session,
        AuditAction.PASSWORD_CHANGED,
        user_id=current_user.id,
        actor_user_id=current_user.id,
    )

    return user


@router.patch("/{user_id}/activate", response_model=UserResponse)
async def activate_user(
    admin: AdminUser,
    user_id: UserId,
    session: Session,
    repository: UserRepositoryDI,
) -> User:
    user = await repository.set_active_user(user_id, True)
    if user is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Пользователь не найден",
        )

    await audit.record(
        session,
        AuditAction.ACTIVATED,
        user_id=user.id,
        actor_user_id=admin.id,
    )

    return user


@router.patch("/{user_id}/deactivate", response_model=UserResponse)
async def deactivate_user(
    admin: AdminUser,
    user_id: UserId,
    session: Session,
    repository: UserRepositoryDI,
) -> User:
    if user_id == admin.id:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Нельзя деактивировать собственную учетную запись",
        )

    user = await repository.set_active_user(user_id, False)
    if user is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Пользователь не найден",
        )


    await audit.record(
        session,
        AuditAction.ACTIVATED,
        user_id=user.id,
        actor_user_id=admin.id,
    )

    return user


@router.get("/{user_id}/audit", response_model=list[AuditLogResponse])
async def read_user_audit_logs(
    _admin: AdminUser,
    user_id: UserId,
    repository: AuditLogRepositoryDI,
    user_repository: UserRepositoryDI,
) -> list[AuditLogResponse]:
    if not await user_repository.get_user_by_id(user_id):
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Пользователь не найден",
        )

    return await repository.get_audit_logs_by_user(user_id)
