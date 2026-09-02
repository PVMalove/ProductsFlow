import uuid
from typing import cast

import pytest
from kernel_domain.result import Result

from application.commands import (
    ActivateProductCommand,
    ActivateProductCommandHandler,
    CreateProductCommand,
    CreateProductCommandHandler,
    DeactivateProductCommand,
    DeactivateProductCommandHandler,
    DeleteProductCommand,
    DeleteProductCommandHandler,
    DeleteProductImageCommand,
    DeleteProductImageCommandHandler,
    UpdateProductCommand,
    UpdateProductCommandHandler,
    UpsertProductImageCommand,
    UpsertProductImageCommandHandler,
)
from application.image_dto import ProductImageMutation
from application.ports import Actor, IdentityUser, OwnerSnapshot, ProductCommandPort
from application.queries import (
    GetProductAuditQuery,
    GetProductAuditQueryHandler,
    GetProductImageQuery,
    GetProductImageQueryHandler,
    GetProductQuery,
    GetProductQueryHandler,
    ListProductsQuery,
    ListProductsQueryHandler,
)
from domain.product import Product
from domain.product_id import ProductId

OWNER_ID = uuid.UUID("00000000-0000-0000-0000-000000000001")


def test_catalog_application_handlers_expose_one_handler_per_operation() -> None:
    command_types = (
        CreateProductCommandHandler,
        UpdateProductCommandHandler,
        ActivateProductCommandHandler,
        DeactivateProductCommandHandler,
        DeleteProductCommandHandler,
        UpsertProductImageCommandHandler,
        DeleteProductImageCommandHandler,
    )
    query_types = (
        GetProductQueryHandler,
        ListProductsQueryHandler,
        GetProductAuditQueryHandler,
        GetProductImageQueryHandler,
    )
    command_dto_types = (
        CreateProductCommand,
        UpdateProductCommand,
        ActivateProductCommand,
        DeactivateProductCommand,
        DeleteProductCommand,
        UpsertProductImageCommand,
        DeleteProductImageCommand,
    )
    query_dto_types = (
        GetProductQuery,
        ListProductsQuery,
        GetProductAuditQuery,
        GetProductImageQuery,
    )

    assert all(hasattr(handler_type, "execute") for handler_type in command_types)
    assert all(hasattr(handler_type, "execute") for handler_type in query_types)
    assert all(not hasattr(handler_type, "handle") for handler_type in command_types)
    assert all(not hasattr(handler_type, "handle") for handler_type in query_types)
    assert all(
        hasattr(dto_type, "__dataclass_fields__") for dto_type in command_dto_types
    )
    assert all(
        hasattr(dto_type, "__dataclass_fields__") for dto_type in query_dto_types
    )


def test_image_command_result_does_not_expose_a_query_view() -> None:
    mutation = ProductImageMutation(replaced=True)

    assert mutation.replaced is True
    assert "view" not in mutation.__dataclass_fields__


class FakeProductRepository:
    def __init__(self) -> None:
        self.created: dict[str, object] | None = None

    async def create(self, **kwargs: object) -> Result[Product]:
        self.created = kwargs
        name = kwargs["name"]
        description = kwargs["description"]
        price = kwargs["price"]
        category = kwargs["category"]
        user_id = kwargs["user_id"]
        assert isinstance(name, str)
        assert isinstance(description, str)
        assert isinstance(price, float)
        assert isinstance(category, str)
        assert isinstance(user_id, uuid.UUID)
        result = Product.create(
            ProductId.generate(),
            name=name,
            description=description,
            price=price,
            category=category,
            user_id=user_id,
        )
        return result


class FakeOwnerReadModel:
    def __init__(self) -> None:
        self.owner: OwnerSnapshot | None = None

    async def get(self, user_id: uuid.UUID) -> OwnerSnapshot | None:
        return self.owner

    async def upsert(self, owner: OwnerSnapshot) -> None:
        self.owner = owner


class FakeIdentityGateway:
    async def fetch_current_user(self, token: str) -> IdentityUser:
        return IdentityUser(id=OWNER_ID, role="user", is_active=True)


@pytest.mark.asyncio
async def test_create_product_command_handler_seeds_owner_and_creates_product() -> None:
    repository = FakeProductRepository()
    owners = FakeOwnerReadModel()
    handler = CreateProductCommandHandler(
        repository=cast(ProductCommandPort, repository),
        owner_read_model=owners,
        identity=FakeIdentityGateway(),
    )

    result = await handler.execute(
        CreateProductCommand(
            actor=Actor(user_id=OWNER_ID, token="token"),
            name="Товар",
            description="Описание",
            price=10.0,
            category="Категория",
        )
    )

    assert result.is_ok
    assert repository.created == {
        "name": "Товар",
        "description": "Описание",
        "price": 10.0,
        "category": "Категория",
        "user_id": OWNER_ID,
    }
    assert owners.owner == OwnerSnapshot(OWNER_ID, "user", True, 0)
