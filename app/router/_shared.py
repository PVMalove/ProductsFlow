from fastapi import HTTPException, status

from app.models import User, UserRole


def _ensure_product_exists[T](entity: T | None) -> T:
    if not entity:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Продукт не найден!",
        )
    return entity


def _is_admin(viewer: User | None) -> bool:
    return viewer is not None and viewer.role == UserRole.ADMIN
