from fastapi import APIRouter

from app.repository import ProductRepositoryDI
from app.schemas import CategoryWithCount

router = APIRouter(prefix="/categories", tags=["categories"])


@router.get(
    "/with-counts",
    response_model=list[CategoryWithCount],
)
async def get_categories_with_count(
    repository: ProductRepositoryDI,
) -> list[CategoryWithCount]:
    return await repository.get_categories_with_count()
