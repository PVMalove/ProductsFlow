"""Get-product-audit query and authorization handler."""

import uuid
from dataclasses import dataclass

from application.authorization import ProductAuthorizer
from application.errors import ProductAccessDeniedError, ProductNotFoundError
from application.ports import (
    Actor,
    IdentityGateway,
    ProductAuditEntry,
    ProductAuditReader,
    ProductQueryPort,
)
from domain.product_id import ProductId


@dataclass(frozen=True)
class GetProductAuditQuery:
    product_id: uuid.UUID
    actor: Actor


class GetProductAuditQueryHandler:
    def __init__(
        self,
        repository: ProductQueryPort,
        audit_reader: ProductAuditReader,
        identity: IdentityGateway,
    ) -> None:
        self._repository = repository
        self._audit_reader = audit_reader
        self._authorizer = ProductAuthorizer(identity)

    async def handle(self, query: GetProductAuditQuery) -> list[ProductAuditEntry]:
        product = await self._repository.get_by_id(ProductId(query.product_id))
        entries = await self._audit_reader.get_by_product(query.product_id)

        if product is not None:
            await self._authorizer.require_owner_or_admin(query.actor, product)
        elif entries and not await self._authorizer.is_admin(query.actor):
            raise ProductAccessDeniedError
        elif not entries:
            raise ProductNotFoundError
        return entries

    async def execute(
        self, product_id: uuid.UUID, *, actor: Actor
    ) -> list[ProductAuditEntry]:
        return await self.handle(
            GetProductAuditQuery(product_id=product_id, actor=actor)
        )
