from kernel_domain.result import Result

from application.authorization import ProductAuthorizer
from application.errors import ProductAccessDeniedError, ProductNotFoundError
from application.ports import (
    Actor,
    IdentityGateway,
    OwnerReadModel,
    OwnerSnapshot,
    ProductAuditEntry,
    ProductAuditReader,
)
from domain.product import Product
from domain.product_id import ProductId
from domain.repositories import Cursor, ProductPage, ProductRepository
from domain.viewer import Viewer
from domain.visibility import ProductVisibilityPolicy


class CreateProduct:
    def __init__(
        self,
        repository: ProductRepository,
        owner_read_model: OwnerReadModel,
        identity: IdentityGateway,
    ) -> None:
        self._repository = repository
        self._owner_read_model = owner_read_model
        self._identity = identity

    async def execute(
        self,
        *,
        actor: Actor,
        name: str,
        description: str,
        price: float,
        category: str,
    ) -> Result[Product]:
        if await self._owner_read_model.get(actor.user_id) is None:
            info = await self._identity.fetch_current_user(actor.token)
            await self._owner_read_model.upsert(
                OwnerSnapshot(
                    user_id=info.id,
                    role=info.role,
                    is_active=info.is_active,
                    last_applied_outbox_id=0,
                )
            )
        return await self._repository.create(
            name=name,
            description=description,
            price=price,
            category=category,
            user_id=actor.user_id,
        )


class ListProducts:
    def __init__(self, repository: ProductRepository) -> None:
        self._repository = repository

    async def execute(
        self,
        *,
        limit: int,
        after: Cursor | None,
        before: Cursor | None,
    ) -> ProductPage:
        return await self._repository.list(limit=limit, after=after, before=before)


class GetProduct:
    def __init__(
        self,
        repository: ProductRepository,
        owner_read_model: OwnerReadModel,
        identity: IdentityGateway,
    ) -> None:
        self._repository = repository
        self._owner_read_model = owner_read_model
        self._authorizer = ProductAuthorizer(identity)
        self._visibility = ProductVisibilityPolicy()

    async def execute(self, product_id: int, *, actor: Actor | None) -> Product:
        product = await self._repository.get_by_id(ProductId(product_id))
        if product is None:
            raise ProductNotFoundError

        if actor is not None and actor.user_id == product.user_id:
            if await self._owner_read_model.get(actor.user_id) is None:
                info = await self._authorizer.fetch_current_user(actor)
                await self._owner_read_model.upsert(
                    OwnerSnapshot(info.id, info.role, info.is_active, 0)
                )
            return product

        owner = await self._owner_read_model.get(product.user_id)
        viewer = Viewer(
            user_id=actor.user_id if actor is not None else None, is_admin=False
        )
        if (
            owner is not None
            and owner.is_active
            and self._visibility.is_visible(viewer, product)
        ):
            return product

        if actor is not None and await self._authorizer.is_admin(actor):
            return product
        raise ProductNotFoundError


class UpdateProduct:
    def __init__(
        self, repository: ProductRepository, identity: IdentityGateway
    ) -> None:
        self._repository = repository
        self._authorizer = ProductAuthorizer(identity)

    async def execute(
        self,
        product_id: int,
        *,
        actor: Actor,
        name: str | None = None,
        description: str | None = None,
        price: float | None = None,
        category: str | None = None,
    ) -> Result[Product]:
        product = await _get_product(self._repository, product_id)
        await self._authorizer.require_owner_or_admin(actor, product)
        result = await self._repository.update(
            product.id,
            name=name,
            description=description,
            price=price,
            category=category,
        )
        if result is None:
            raise ProductNotFoundError
        return result


class ActivateProduct:
    def __init__(
        self, repository: ProductRepository, identity: IdentityGateway
    ) -> None:
        self._repository = repository
        self._authorizer = ProductAuthorizer(identity)

    async def execute(self, product_id: int, *, actor: Actor) -> Result[Product]:
        product = await _get_product(self._repository, product_id)
        await self._authorizer.require_owner_or_admin(actor, product)
        result = await self._repository.activate(product.id)
        if result is None:
            raise ProductNotFoundError
        return result


class DeactivateProduct:
    def __init__(
        self, repository: ProductRepository, identity: IdentityGateway
    ) -> None:
        self._repository = repository
        self._authorizer = ProductAuthorizer(identity)

    async def execute(self, product_id: int, *, actor: Actor) -> Result[Product]:
        product = await _get_product(self._repository, product_id)
        await self._authorizer.require_owner_or_admin(actor, product)
        result = await self._repository.deactivate(product.id)
        if result is None:
            raise ProductNotFoundError
        return result


class DeleteProduct:
    def __init__(
        self, repository: ProductRepository, identity: IdentityGateway
    ) -> None:
        self._repository = repository
        self._authorizer = ProductAuthorizer(identity)

    async def execute(self, product_id: int, *, actor: Actor) -> Product:
        product = await _get_product(self._repository, product_id)
        await self._authorizer.require_owner_or_admin(actor, product)
        deleted = await self._repository.delete(product.id)
        if deleted is None:
            raise ProductNotFoundError
        return deleted


class GetProductAudit:
    def __init__(
        self,
        repository: ProductRepository,
        audit_reader: ProductAuditReader,
        identity: IdentityGateway,
    ) -> None:
        self._repository = repository
        self._audit_reader = audit_reader
        self._authorizer = ProductAuthorizer(identity)

    async def execute(
        self, product_id: int, *, actor: Actor
    ) -> list[ProductAuditEntry]:
        product = await self._repository.get_by_id(ProductId(product_id))
        entries = await self._audit_reader.get_by_product(product_id)

        if product is not None:
            await self._authorizer.require_owner_or_admin(actor, product)
        elif entries and not await self._authorizer.is_admin(actor):
            raise ProductAccessDeniedError
        elif not entries:
            raise ProductNotFoundError
        return entries


async def _get_product(repository: ProductRepository, product_id: int) -> Product:
    product = await repository.get_by_id(ProductId(product_id))
    if product is None:
        raise ProductNotFoundError
    return product


__all__ = [
    "ActivateProduct",
    "CreateProduct",
    "DeactivateProduct",
    "DeleteProduct",
    "GetProduct",
    "GetProductAudit",
    "ListProducts",
    "UpdateProduct",
]
