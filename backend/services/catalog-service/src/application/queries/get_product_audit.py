# ruff: noqa: E501
"""Get-product-audit query and authorization handler."""

import uuid
from dataclasses import dataclass

from kernel_domain.result import Result

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
    """DTO для получения истории аудита товара."""

    product_id: uuid.UUID
    actor: Actor


class GetProductAuditQueryHandler:
    """
    Business Logic Summary

    Context & Purpose: Получение логов изменений (аудита) по конкретному товару.
    Validations: Требуются права владельца или администратора.
    Data Sourcing: Данные берутся из ProductAuditReader.
    """

    def __init__(
        self,
        repository: ProductQueryPort,
        audit_reader: ProductAuditReader,
        identity: IdentityGateway,
    ) -> None:
        self._repository = repository
        self._audit_reader = audit_reader
        self._authorizer = ProductAuthorizer(identity)

    async def execute(
        self, query: GetProductAuditQuery
    ) -> Result[list[ProductAuditEntry]]:
        product = await self._repository.get_by_id(ProductId(query.product_id))
        entries = await self._audit_reader.get_by_product(query.product_id)

        if product is not None:
            await self._authorizer.require_owner_or_admin(query.actor, product)
        elif entries and not await self._authorizer.is_admin(query.actor):
            raise ProductAccessDeniedError
        elif not entries:
            raise ProductNotFoundError
        return Result[list[ProductAuditEntry]].ok(entries)
