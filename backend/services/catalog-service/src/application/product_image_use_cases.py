"""Compatibility adapters for the pre-CQRS product-image imports."""

from application.commands import (
    DeleteProductImageCommandHandler as DeleteProductImage,
)
from application.commands import (
    UpsertProductImageCommandHandler as UpsertProductImage,
)
from application.errors import ProductImageNotFoundError
from application.image_dto import ProductImageMutation, ProductImageView
from application.queries import GetProductImageQueryHandler as GetProductImage

__all__ = [
    "DeleteProductImage",
    "GetProductImage",
    "ProductImageMutation",
    "ProductImageNotFoundError",
    "ProductImageView",
    "UpsertProductImage",
]
