import uuid
from datetime import datetime, timezone

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
    UpdateProductCommand,
    UpdateProductCommandHandler,
)
from application.errors import ProductAccessDeniedError, ProductNotFoundError
from application.ports import (
    Actor,
    IdentityUser,
    OwnerSnapshot,
    ProductAuditAction,
    ProductAuditEntry,
)
from application.queries import (
    GetProductAuditQuery,
    GetProductAuditQueryHandler,
    GetProductQuery,
    GetProductQueryHandler,
    ListProductsQuery,
    ListProductsQueryHandler,
)
from contracts.product import ProductView
from domain.product import Product
from domain.product_id import ProductId
from domain.product_image import ProductImage
from domain.repositories import PageInfo, ProductPage

OWNER_ID = uuid.uuid4()
OTHER_ID = uuid.uuid4()


def _product(
    *,
    product_id: uuid.UUID = uuid.UUID("00000000-0000-0000-0000-000000000001"),
    user_id: uuid.UUID = OWNER_ID,
) -> Product:
    result = Product.create(
        ProductId(product_id),
        name="Товар",
        description="Описание",
        price=10.0,
        category="Категория",
        user_id=user_id,
    )
    assert result.is_ok
    return result.value


class FakeRepository:
    def __init__(self, product: Product | None = None) -> None:
        self.product = product
        self.created: dict[str, object] | None = None
        self.updated: dict[str, object] | None = None
        self.deleted = False

    async def create(self, **kwargs: object) -> Result[Product]:
        self.created = kwargs
        assert self.product is not None
        return Result.ok(self.product)

    async def get_by_id(self, product_id: ProductId) -> Product | None:
        return self.product if self.product and self.product.id == product_id else None

    async def update(self, product_id: ProductId, **kwargs: object) -> Result[Product]:
        self.updated = kwargs
        assert self.product is not None
        return Result.ok(self.product)

    async def activate(self, product_id: ProductId) -> Result[Product]:
        assert self.product is not None
        return Result.ok(self.product)

    async def deactivate(self, product_id: ProductId) -> Result[Product]:
        assert self.product is not None
        return Result.ok(self.product)

    async def delete(self, product_id: ProductId) -> Product | None:
        self.deleted = True
        return self.product

    async def get_product_image(self, product_id: ProductId) -> ProductImage | None:
        return None

    async def upsert_product_image(
        self,
        product_id: ProductId,
        *,
        s3_key: str,
        content_type: str,
        size_bytes: int,
        actor_user_id: uuid.UUID,
    ) -> ProductImage:
        raise NotImplementedError

    async def delete_product_image(
        self, product_id: ProductId, *, actor_user_id: uuid.UUID
    ) -> None:
        raise NotImplementedError

    async def list(self, **kwargs: object) -> ProductPage:
        return ProductPage(
            items=[self.product] if self.product is not None else [],
            page_info=PageInfo(None, None, False, False),
        )


class FakeOwnerReadModel:
    def __init__(self, owner: OwnerSnapshot | None = None) -> None:
        self.owner = owner
        self.upserts: list[OwnerSnapshot] = []

    async def get(self, user_id: uuid.UUID) -> OwnerSnapshot | None:
        return self.owner if self.owner and self.owner.user_id == user_id else None

    async def upsert(self, owner: OwnerSnapshot) -> None:
        self.upserts.append(owner)
        self.owner = owner

    async def find_by_role(self, role: str) -> OwnerSnapshot | None:
        return self.owner if self.owner and self.owner.role == role else None


class FakeIdentity:
    def __init__(self, *, role: str = "user") -> None:
        self.role = role
        self.fetches = 0

    async def fetch_current_user(self, token: str) -> IdentityUser:
        self.fetches += 1
        return IdentityUser(id=OWNER_ID, role=self.role, is_active=True)


class FakeAuditReader:
    async def get_by_product(self, product_id: uuid.UUID) -> list[ProductAuditEntry]:
        return [
            ProductAuditEntry(
                id=1,
                product_id=product_id,
                actor_user_id=None,
                action=ProductAuditAction.CREATED,
                description="Создан",
                created_at=datetime.now(timezone.utc),
            )
        ]


def _actor(user_id: uuid.UUID = OWNER_ID) -> Actor:
    return Actor(user_id=user_id, token=f"token-{user_id}")


def _dependencies(
    *, product: Product | None = None, owner: OwnerSnapshot | None = None
) -> tuple[FakeRepository, FakeOwnerReadModel, FakeIdentity]:
    return FakeRepository(product), FakeOwnerReadModel(owner), FakeIdentity()


async def test_create_product_seeds_owner_before_creating() -> None:
    product = _product()
    repo, owners, identity = _dependencies(product=product)
    handler = CreateProductCommandHandler(repo, owners, identity)

    result = await handler.execute(
        CreateProductCommand(
            actor=_actor(),
            name="Товар",
            description="",
            price=10.0,
            category="Категория",
        )
    )

    assert result.is_ok
    assert result.value == ProductView.from_domain(product)
    assert owners.upserts == [OwnerSnapshot(OWNER_ID, "user", True, 0)]
    assert identity.fetches == 1
    assert repo.created == {
        "name": "Товар",
        "description": "",
        "price": 10.0,
        "category": "Категория",
        "user_id": OWNER_ID,
    }


async def test_get_product_denies_inactive_owner_to_other_viewer() -> None:
    product = _product()
    repo, owners, identity = _dependencies(
        product=product,
        owner=OwnerSnapshot(OWNER_ID, "user", False, 1),
    )
    handler = GetProductQueryHandler(repo, owners, identity)

    with pytest.raises(ProductNotFoundError):
        await handler.execute(
            GetProductQuery(product_id=product.id.value, actor=_actor(OTHER_ID))
        )


async def test_get_product_returns_ok_result_for_owner() -> None:
    product = _product()
    repo, owners, identity = _dependencies(
        product=product, owner=OwnerSnapshot(OWNER_ID, "user", True, 1)
    )
    handler = GetProductQueryHandler(repo, owners, identity)

    result = await handler.execute(
        GetProductQuery(product_id=product.id.value, actor=_actor(OWNER_ID))
    )

    assert result.is_ok
    assert result.value == ProductView.from_domain(product)


async def test_update_product_allows_owner_and_keeps_partial_fields() -> None:
    product = _product()
    repo, _owners, identity = _dependencies(
        product=product, owner=OwnerSnapshot(OWNER_ID, "user", True, 1)
    )
    handler = UpdateProductCommandHandler(repo, identity)

    result = await handler.execute(
        UpdateProductCommand(
            product_id=product.id.value,
            actor=_actor(),
            name=None,
            description=None,
            price=42.0,
            category=None,
        )
    )

    assert result.is_ok
    assert result.value == ProductView.from_domain(product)
    assert repo.updated == {
        "name": None,
        "description": None,
        "price": 42.0,
        "category": None,
    }


async def test_delete_product_denies_non_owner_when_identity_is_not_admin() -> None:
    product = _product()
    repo, owners, identity = _dependencies(
        product=product, owner=OwnerSnapshot(OWNER_ID, "user", True, 1)
    )
    handler = DeleteProductCommandHandler(repo, identity)

    with pytest.raises(ProductAccessDeniedError):
        await handler.execute(
            DeleteProductCommand(product_id=product.id.value, actor=_actor(OTHER_ID))
        )

    assert repo.deleted is False
    assert owners.upserts == []


async def test_delete_product_by_owner_returns_ok_result_with_none_value() -> None:
    product = _product()
    repo, _owners, identity = _dependencies(
        product=product, owner=OwnerSnapshot(OWNER_ID, "user", True, 1)
    )
    handler = DeleteProductCommandHandler(repo, identity)

    result = await handler.execute(
        DeleteProductCommand(product_id=product.id.value, actor=_actor())
    )

    assert result.is_ok
    assert result.value is None
    assert repo.deleted is True


async def test_remaining_handlers_delegate_to_repository_and_audit_port() -> None:
    product = _product()
    repo, _owners, identity = _dependencies(
        product=product, owner=OwnerSnapshot(OWNER_ID, "user", True, 1)
    )
    actor = _actor()

    activate_result = await ActivateProductCommandHandler(repo, identity).execute(
        ActivateProductCommand(product_id=product.id.value, actor=actor)
    )
    assert activate_result.is_ok
    assert activate_result.value == ProductView.from_domain(product)

    deactivate_result = await DeactivateProductCommandHandler(repo, identity).execute(
        DeactivateProductCommand(product_id=product.id.value, actor=actor)
    )
    assert deactivate_result.is_ok
    assert deactivate_result.value == ProductView.from_domain(product)

    list_result = await ListProductsQueryHandler(repo).execute(
        ListProductsQuery(limit=20, after=None, before=None)
    )
    audit = await GetProductAuditQueryHandler(
        repo, FakeAuditReader(), identity
    ).execute(GetProductAuditQuery(product_id=product.id.value, actor=actor))

    assert list_result.is_ok
    assert list_result.value.items == [ProductView.from_domain(product)]
    assert audit[0].action == "created"
