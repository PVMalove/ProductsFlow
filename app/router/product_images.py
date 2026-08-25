from fastapi import APIRouter, HTTPException, status

from app.repository import ProductRepositoryDI
from app.router.product_visibility import ensure_product_exists, is_admin
from app.schemas import ProductId, ProductImageResponse
from app.security import OptionalUser
from app.settings import settings
from app.storage import StorageDI

router = APIRouter(prefix="/products", tags=["products"])


@router.get(
    "/{product_id}/image",
    response_model=ProductImageResponse,
)
async def get_product_image(
    product_id: ProductId,
    repository: ProductRepositoryDI,
    storage: StorageDI,
    viewer: OptionalUser,
) -> ProductImageResponse:
    ensure_product_exists(
        await repository.get_product_by_id(
            product_id,
            viewer_is_admin=is_admin(viewer),
            viewer_id=viewer.id if viewer is not None else None,
        )
    )
    image = await repository.get_product_image_by_id(product_id)
    if image is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="У товара нет картинки!",
        )
    return ProductImageResponse(
        url=storage.build_public_url(
            settings.minio_bucket_name_product,
            image.s3_key,
            int(image.updated_at.timestamp()),
        ),
        updated_at=image.updated_at,
    )
