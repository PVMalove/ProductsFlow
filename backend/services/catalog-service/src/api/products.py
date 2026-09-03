import uuid
from typing import Annotated

from fastapi import APIRouter, Depends, status
from kernel_domain.result import Result
from kernel_platform.http.envelope import ApiResponse
from kernel_platform.http.match import match_created, match_page, match_result

from api.dependencies import (
    ActivateProductDI,
    CreateProductDI,
    DeactivateProductDI,
    DeleteProductDI,
    GetProductAuditDI,
    GetProductDI,
    ListProductsDI,
    OptionalAuth,
    RequiredAuth,
    UpdateProductDI,
    to_actor,
)
from api.schemas import (
    ProductActivateRequest,
    ProductAuditRequest,
    ProductCreateRequest,
    ProductDeactivateRequest,
    ProductDeleteRequest,
    ProductGetRequest,
    ProductListRequest,
    ProductUpdateRequest,
)
from application.ports import ProductAuditEntry
from contracts.product import ProductView

router = APIRouter(prefix="/api/v1/products", tags=["products"])


@router.post(
    "",
    response_model=ApiResponse[ProductView],
    status_code=status.HTTP_201_CREATED,
)
async def create_product(
    request: ProductCreateRequest,
    auth: RequiredAuth,
    handler: CreateProductDI,
) -> ApiResponse[ProductView]:
    command = request.to_command(actor=to_actor(auth))
    result: Result[ProductView] = await handler.execute(command)
    return match_created(result)


@router.get("", response_model=ApiResponse[list[ProductView]])
async def list_products(
    request: Annotated[ProductListRequest, Depends()],
    handler: ListProductsDI,
) -> ApiResponse[list[ProductView]]:
    query = request.to_query()
    result = await handler.execute(query)
    return match_page(result)


@router.get("/{product_id}", response_model=ApiResponse[ProductView])
async def get_product(
    request: Annotated[ProductGetRequest, Depends()],
    auth: OptionalAuth,
    handler: GetProductDI,
) -> ApiResponse[ProductView]:
    query = request.to_query(actor=to_actor(auth) if auth is not None else None)
    result: Result[ProductView] = await handler.execute(query)
    return match_result(result)


@router.patch("/{product_id}", response_model=ApiResponse[ProductView])
async def update_product(
    product_id: uuid.UUID,
    request: ProductUpdateRequest,
    auth: RequiredAuth,
    handler: UpdateProductDI,
) -> ApiResponse[ProductView]:
    command = request.to_command(product_id=product_id, actor=to_actor(auth))
    result: Result[ProductView] = await handler.execute(command)
    return match_result(result)


@router.patch("/{product_id}/activate", response_model=ApiResponse[ProductView])
async def activate_product(
    request: Annotated[ProductActivateRequest, Depends()],
    auth: RequiredAuth,
    handler: ActivateProductDI,
) -> ApiResponse[ProductView]:
    command = request.to_command(actor=to_actor(auth))
    result: Result[ProductView] = await handler.execute(command)
    return match_result(result)


@router.patch("/{product_id}/deactivate", response_model=ApiResponse[ProductView])
async def deactivate_product(
    request: Annotated[ProductDeactivateRequest, Depends()],
    auth: RequiredAuth,
    handler: DeactivateProductDI,
) -> ApiResponse[ProductView]:
    command = request.to_command(actor=to_actor(auth))
    result: Result[ProductView] = await handler.execute(command)
    return match_result(result)


@router.delete("/{product_id}", response_model=ApiResponse[None])
async def delete_product(
    request: Annotated[ProductDeleteRequest, Depends()],
    auth: RequiredAuth,
    handler: DeleteProductDI,
) -> ApiResponse[None]:
    command = request.to_command(actor=to_actor(auth))
    result: Result[None] = await handler.execute(command)
    return match_result(result)


@router.get("/{product_id}/audit", response_model=ApiResponse[list[ProductAuditEntry]])
async def get_product_audit(
    request: Annotated[ProductAuditRequest, Depends()],
    auth: RequiredAuth,
    handler: GetProductAuditDI,
) -> ApiResponse[list[ProductAuditEntry]]:
    query = request.to_query(actor=to_actor(auth))
    result: Result[list[ProductAuditEntry]] = await handler.execute(query)
    return match_result(result)
