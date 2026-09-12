import uuid

from fastapi import APIRouter, status
from kernel_domain.result import Result
from kernel_platform.http.envelope import ApiResponse
from kernel_platform.http.match import match_created, match_result
from kernel_platform.security import Actor, ActorRole

from api.dependencies import (
    AddCartLineDI,
    GetCartDI,
    RemoveCartLineDI,
    UpdateCartLineQuantityDI,
)
from api.schemas import AddCartLineRequest, UpdateCartLineRequest, to_remove_command
from application.queries import GetCartQuery
from contracts.cart import CartLineView, CartView
from infrastructure.security.auth import RequiredAuth

router = APIRouter(prefix="/api/v1/cart", tags=["cart"])


def _actor(auth: RequiredAuth) -> Actor:
    # order-service допускает любого аутентифицированного пользователя ко
    # всем операциям над СОБСТВЕННОЙ корзиной — роль не проверяется
    # (архитектурный бриф issue #369 D2).
    return Actor(id=auth.user_id, role=ActorRole.USER)


@router.get("", response_model=ApiResponse[CartView], status_code=status.HTTP_200_OK)
async def get_cart(auth: RequiredAuth, handler: GetCartDI) -> ApiResponse[CartView]:
    result: Result[CartView] = await handler.execute(GetCartQuery(user_id=auth.user_id))
    return match_result(result)


@router.post(
    "/lines",
    response_model=ApiResponse[CartLineView],
    status_code=status.HTTP_201_CREATED,
)
async def add_cart_line(
    request: AddCartLineRequest, auth: RequiredAuth, handler: AddCartLineDI
) -> ApiResponse[CartLineView]:
    command = request.to_command(actor=_actor(auth))
    result: Result[CartLineView] = await handler.execute(command)
    return match_created(result)


@router.patch(
    "/lines/{line_id}",
    response_model=ApiResponse[CartLineView],
    status_code=status.HTTP_200_OK,
)
async def update_cart_line(
    line_id: uuid.UUID,
    request: UpdateCartLineRequest,
    auth: RequiredAuth,
    handler: UpdateCartLineQuantityDI,
) -> ApiResponse[CartLineView]:
    command = request.to_command(line_id=line_id, actor=_actor(auth))
    result: Result[CartLineView] = await handler.execute(command)
    return match_result(result)


@router.delete(
    "/lines/{line_id}",
    response_model=ApiResponse[None],
    status_code=status.HTTP_200_OK,
)
async def remove_cart_line(
    line_id: uuid.UUID, auth: RequiredAuth, handler: RemoveCartLineDI
) -> ApiResponse[None]:
    command = to_remove_command(line_id=line_id, actor=_actor(auth))
    result: Result[None] = await handler.execute(command)
    return match_result(result)
