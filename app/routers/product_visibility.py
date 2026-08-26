from fastapi import HTTPException, status

from app.models import Product, User, UserRole
from app.schemas import ProductResponse


def ensure_product_exists[T](entity: T | None) -> T:
    if not entity:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Продукт не найден!",
        )
    return entity


def is_admin(viewer: User | None) -> bool:
    return viewer is not None and viewer.role == UserRole.ADMIN


def ensure_owner_or_admin(
    product: Product | ProductResponse, current_user: User
) -> None:
    is_owner = product.user_id == current_user.id
    is_admin_owner = current_user.role == UserRole.ADMIN
    if not (is_owner or is_admin_owner):
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Нет прав на этот продукт!",
        )
