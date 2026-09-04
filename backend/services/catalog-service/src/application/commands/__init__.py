"""Публичный command-side интерфейс для application use case'ов catalog."""

from application.commands.activate_product import (
    ActivateProductCommand,
    ActivateProductCommandHandler,
)
from application.commands.create_product import (
    CreateProductCommand,
    CreateProductCommandHandler,
)
from application.commands.deactivate_product import (
    DeactivateProductCommand,
    DeactivateProductCommandHandler,
)
from application.commands.delete_product import (
    DeleteProductCommand,
    DeleteProductCommandHandler,
)
from application.commands.delete_product_image import (
    DeleteProductImageCommand,
    DeleteProductImageCommandHandler,
)
from application.commands.update_product import (
    UpdateProductCommand,
    UpdateProductCommandHandler,
)
from application.commands.upsert_product_image import (
    IMAGE_KEY_TEMPLATE,
    SEED_KEY_PREFIX,
    UpsertProductImageCommand,
    UpsertProductImageCommandHandler,
)

__all__ = [
    "ActivateProductCommand",
    "ActivateProductCommandHandler",
    "CreateProductCommand",
    "CreateProductCommandHandler",
    "DeactivateProductCommand",
    "DeactivateProductCommandHandler",
    "DeleteProductCommand",
    "DeleteProductCommandHandler",
    "DeleteProductImageCommand",
    "DeleteProductImageCommandHandler",
    "IMAGE_KEY_TEMPLATE",
    "SEED_KEY_PREFIX",
    "UpdateProductCommand",
    "UpdateProductCommandHandler",
    "UpsertProductImageCommand",
    "UpsertProductImageCommandHandler",
]
