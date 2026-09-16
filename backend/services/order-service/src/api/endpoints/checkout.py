from typing import Annotated

from fastapi import APIRouter, Header, status
from kernel_domain.result import Result
from kernel_platform.http.envelope import ApiResponse
from kernel_platform.http.match import match_created
from kernel_platform.security import Actor, ActorRole

from api.dependencies import CheckoutDI
from application.commands import CheckoutCommand
from contracts.order import OrderView
from infrastructure.security.auth import RequiredActiveUser

router = APIRouter(prefix="/api/v1/checkout", tags=["checkout"])


@router.post(
    "", response_model=ApiResponse[OrderView], status_code=status.HTTP_201_CREATED
)
async def checkout(
    auth: RequiredActiveUser,
    handler: CheckoutDI,
    idempotency_key: Annotated[str, Header(alias="Idempotency-Key", min_length=1)],
) -> ApiResponse[OrderView]:
    command = CheckoutCommand(
        actor=Actor(id=auth.user_id, role=ActorRole.USER),
        idempotency_key=idempotency_key,
        bearer_token=auth.token,
    )
    result: Result[OrderView] = await handler.execute(command)
    return match_created(result)
