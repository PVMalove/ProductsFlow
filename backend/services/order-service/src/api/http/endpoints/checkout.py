from typing import Annotated

from fastapi import APIRouter, Depends, status
from kernel_domain.result import Result
from kernel_platform.http.envelope import ApiResponse
from kernel_platform.http.match import match_created
from kernel_platform.security import Actor, ActorRole

from api.http.dependencies import CheckoutDI
from api.http.schemas import CheckoutRequest
from application.commands import CheckoutCommand
from contracts.order import OrderView
from infrastructure.security.auth import RequiredActiveUser

router = APIRouter(prefix="/api/v1/checkout", tags=["checkout"])


@router.post(
    "", response_model=ApiResponse[OrderView], status_code=status.HTTP_201_CREATED
)
async def checkout(
    request: Annotated[CheckoutRequest, Depends()],
    auth: RequiredActiveUser,
    handler: CheckoutDI,
) -> ApiResponse[OrderView]:
    command: CheckoutCommand = request.to_command(
        actor=_actor(auth),
        bearer_token=auth.token,
    )
    result: Result[OrderView] = await handler.execute(command)
    return match_created(result)


def _actor(auth: RequiredActiveUser) -> Actor:
    return Actor(id=auth.user_id, role=ActorRole.USER)
