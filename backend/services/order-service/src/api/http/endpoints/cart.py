import uuid
from typing import Annotated

from fastapi import APIRouter, Depends, status
from kernel_domain.result import Result
from kernel_platform.http.envelope import ApiResponse
from kernel_platform.http.match import match_created, match_result
from kernel_platform.security import Actor, ActorRole

from api.http.dependencies import (
    AddCartLineDI,
    GetCartDI,
    RemoveCartLineDI,
    UpdateCartLineQuantityDI,
)
from api.http.schemas import (
    AddCartLineRequest,
    GetCartRequest,
    RemoveCartLineRequest,
    UpdateCartLineRequest,
)
from application.commands import (
    AddCartLineCommand,
    RemoveCartLineCommand,
    UpdateCartLineQuantityCommand,
)
from application.queries import GetCartQuery
from contracts.cart import CartLineView, CartView
from infrastructure.security.auth import RequiredAuth

router = APIRouter(prefix="/api/v1/cart", tags=["cart"])


@router.get("", response_model=ApiResponse[CartView], status_code=status.HTTP_200_OK)
async def get_cart(
    request: Annotated[GetCartRequest, Depends()],
    auth: RequiredAuth,
    handler: GetCartDI,
) -> ApiResponse[CartView]:
    query: GetCartQuery = request.to_query(actor=_actor(auth))
    result: Result[CartView] = await handler.execute(query)
    return match_result(result)


@router.post(
    "/lines",
    response_model=ApiResponse[CartLineView],
    status_code=status.HTTP_201_CREATED,
)
async def add_cart_line(
    request: AddCartLineRequest, auth: RequiredAuth, handler: AddCartLineDI
) -> ApiResponse[CartLineView]:
    command: AddCartLineCommand = request.to_command(actor=_actor(auth))
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
    command: UpdateCartLineQuantityCommand = request.to_command(
        line_id=line_id, actor=_actor(auth)
    )
    result: Result[CartLineView] = await handler.execute(command)
    return match_result(result)


@router.delete(
    "/lines/{line_id}",
    response_model=ApiResponse[None],
    status_code=status.HTTP_200_OK,
)
async def remove_cart_line(
    request: Annotated[RemoveCartLineRequest, Depends()],
    auth: RequiredAuth,
    handler: RemoveCartLineDI,
) -> ApiResponse[None]:
    command: RemoveCartLineCommand = request.to_command(actor=_actor(auth))
    result: Result[None] = await handler.execute(command)
    return match_result(result)


def _actor(auth: RequiredAuth) -> Actor:
    # order-service допускает любого аутентифицированного пользователя ко
    # всем операциям над СОБСТВЕННОЙ корзиной — роль не проверяется.
    return Actor(id=auth.user_id, role=ActorRole.USER)
