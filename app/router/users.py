from fastapi import APIRouter, HTTPException, status

from app.models import User
from app.repository import UserRepositoryDI
from app.schemas import PasswordChange, UserId, UserResponse
from app.security import AdminUser, CurrentUser, hash_password, verify_password

router = APIRouter(prefix="/users", tags=["users"])


@router.get("/", response_model=list[UserResponse])
async def list_users(
    _admin: AdminUser,
    repository: UserRepositoryDI,
) -> list[UserResponse]:
    return await repository.get_all_users()


@router.get("/me", response_model=UserResponse)
async def read_current_user(current_user: CurrentUser) -> CurrentUser:
    return current_user


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
    _admin: AdminUser,
    user_id: UserId,
    repository: UserRepositoryDI,
) -> User:
    user = await repository.set_active_user(user_id, True)
    if user is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Пользователь не найден",
        )
    return user


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

    user = await repository.set_active_user(user_id, False)
    if user is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Пользователь не найден",
        )
    return user
