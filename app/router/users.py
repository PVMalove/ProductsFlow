from fastapi import APIRouter, HTTPException, status

from app.repository import UserRepositoryDI
from app.schemas import PasswordChange, UserResponse
from app.security import CurrentUser, hash_password, verify_password

router = APIRouter(prefix="/users", tags=["users"])


@router.get("/me", response_model=UserResponse)
async def read_current_user(current_user: CurrentUser) -> CurrentUser:
    return current_user


@router.patch("/me/password", response_model=UserResponse)
async def update_password(
    request: PasswordChange,
    current_user: CurrentUser,
    repository: UserRepositoryDI,
):
    if not verify_password(request.old_password, current_user.password_hash):
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Текущий пароль указан неверно",
        )

    return await repository.update_user_password(
        current_user.id,
        hash_password(request.new_password),
    )
