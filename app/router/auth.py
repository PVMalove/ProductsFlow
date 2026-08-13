from typing import Annotated

from fastapi import APIRouter, Depends, HTTPException, status
from fastapi.security import OAuth2PasswordRequestForm

from app import audit
from app.db import Session
from app.models import AuditAction, User
from app.repository import UserRepositoryDI
from app.schemas import TokenResponse, UserCreate, UserResponse
from app.security import create_access_token, hash_password, verify_password

router = APIRouter(prefix="/auth", tags=["auth"])


@router.post(
    "/register",
    response_model=UserResponse,
    status_code=status.HTTP_201_CREATED,
)
async def register_user(
    request: UserCreate, session: Session, repository: UserRepositoryDI
) -> User:
    user = await repository.create(
        username=request.username,
        password_hash=hash_password(request.password),
    )
    await audit.record(
        session, AuditAction.REGISTERED, user_id=user.id, actor_user_id=user.id
    )
    return user


@router.post("/login", response_model=TokenResponse, status_code=status.HTTP_200_OK)
async def login_for_access_token(
    form_data: Annotated[OAuth2PasswordRequestForm, Depends()],
    repository: UserRepositoryDI,
) -> TokenResponse:
    user = await repository.get_user_by_name(form_data.username)
    if user is None or not verify_password(form_data.password, user.password_hash):
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Неверное имя пользователя или пароль",
            headers={"WWW-Authenticate": "Bearer"},
        )
    if not user.is_active:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Учётная запись отключена",
        )
    return TokenResponse(access_token=create_access_token(user.id))
