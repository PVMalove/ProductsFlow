import uuid

from fastapi import APIRouter, status
from kernel_domain.result import Result
from kernel_platform.http.envelope import ApiResponse
from kernel_platform.http.match import match_result
from kernel_platform.security import Actor, ActorRole

from api.http.dependencies import CancelOrderDI
from application.commands import CancelOrderCommand
from contracts.order import OrderView
from infrastructure.security.auth import RequiredActiveUser

router = APIRouter(prefix="/api/v1/orders", tags=["orders"])


@router.post(
    "/{order_id}/cancel",
    response_model=ApiResponse[OrderView],
    status_code=status.HTTP_200_OK,
)
async def cancel_order(
    order_id: uuid.UUID, auth: RequiredActiveUser, handler: CancelOrderDI
) -> ApiResponse[OrderView]:
    # issue #377, D6: как checkout — JWT + синхронная сверка активности
    # пользователя (fail-closed 503 при недоступном identity, ADR 0016).
    command = CancelOrderCommand(
        actor=Actor(id=auth.user_id, role=ActorRole.USER), order_id=order_id
    )
    result: Result[OrderView] = await handler.execute(command)
    return match_result(result)
