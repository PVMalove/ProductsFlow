from typing import Annotated

from fastapi import APIRouter, Depends, status
from fastapi.security import OAuth2PasswordRequestForm
from kernel_domain.result import Result
from kernel_platform.http.envelope import ApiResponse
from kernel_platform.http.match import match_created

from api.dependencies import LoginDI, RegisterUserDI
from api.errors import raise_command_error
from api.schemas import TokenResponse, UserCreate
from application.commands import LoginCommand
from contracts.user import UserView
from core.security.tokens import create_access_token

router = APIRouter(prefix="/api/v1/auth", tags=["auth"])


@router.post(
    "/register",
    response_model=ApiResponse[UserView],
    status_code=status.HTTP_201_CREATED,
)
async def register_user(
    request: UserCreate, handler: RegisterUserDI
) -> ApiResponse[UserView]:
    command = request.to_command()
    result: Result[UserView] = await handler.execute(command)
    return match_created(result)


@router.post("/login", response_model=TokenResponse)
async def login_for_access_token(
    form_data: Annotated[OAuth2PasswordRequestForm, Depends()], handler: LoginDI
) -> TokenResponse:
    """OAuth2 password-grant login stays a flat protocol endpoint for
    `OAuth2PasswordBearer`/Swagger UI (ADR 0033) — not migrated to the BFF
    envelope."""
    result = await handler.execute(
        LoginCommand(email=form_data.username, password=form_data.password)
    )
    if result.is_err:
        raise_command_error(result)
    return TokenResponse(access_token=create_access_token(result.value.id.value))
