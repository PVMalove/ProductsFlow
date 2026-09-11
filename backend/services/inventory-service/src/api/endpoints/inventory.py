import uuid

from fastapi import APIRouter, status
from kernel_domain.result import Result
from kernel_platform.http.envelope import ApiResponse
from kernel_platform.http.match import match_result

from api.dependencies import AdjustInventoryStockDI
from api.schemas import InventoryAdjustmentRequest
from contracts.inventory import InventoryView
from infrastructure.security.auth import AdminActor

router = APIRouter(prefix="/api/v1/inventory", tags=["inventory"])


@router.post(
    "/{product_id}/adjustments",
    response_model=ApiResponse[InventoryView],
    status_code=status.HTTP_200_OK,
)
async def adjust_inventory_stock(
    product_id: uuid.UUID,
    request: InventoryAdjustmentRequest,
    actor: AdminActor,
    handler: AdjustInventoryStockDI,
) -> ApiResponse[InventoryView]:
    command = request.to_command(product_id=product_id, actor=actor)
    result: Result[InventoryView] = await handler.execute(command)
    return match_result(result)
