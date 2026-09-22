from typing import Annotated

from fastapi import APIRouter, Depends, status
from fastapi.security import OAuth2PasswordRequestForm
from kernel_domain.result import Result
from kernel_platform.http.envelope import ApiResponse
from kernel_platform.http.match import match_created

from api.errors import raise_command_error
from api.http.dependencies import LoginDI, RegisterUserDI
from api.http.schemas import TokenResponse, UserCreate
from application.commands import LoginCommand, RegisterUserCommand
from contracts.user import UserView
from core.security.tokens import create_access_token
from domain.entities.user import User

router = APIRouter(prefix="/api/v1/auth", tags=["auth"])


@router.post(
    "/register",
    response_model=ApiResponse[UserView],
    status_code=status.HTTP_201_CREATED,
)
async def register_user(
    request: UserCreate, handler: RegisterUserDI
) -> ApiResponse[UserView]:
    command: RegisterUserCommand = request.to_command()
    result: Result[UserView] = await handler.execute(command)
    return match_created(result)


@router.post("/login", response_model=TokenResponse)
async def login_for_access_token(
    form_data: Annotated[OAuth2PasswordRequestForm, Depends()], handler: LoginDI
) -> TokenResponse:
    """Логин через OAuth2 password-grant остаётся плоским протокольным
    эндпоинтом для `OAuth2PasswordBearer`/Swagger UI (ADR 0002) — не
    мигрирован на BFF-конверт."""
    command: LoginCommand = LoginCommand(
        email=form_data.username, password=form_data.password
    )
    result: Result[User] = await handler.execute(command)
    if result.is_err:
        raise_command_error(result)
    return TokenResponse(access_token=create_access_token(result.value.id.value))
