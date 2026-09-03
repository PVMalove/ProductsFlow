# ruff: noqa: E501
"""Deactivate-product command and handler."""

import uuid
from dataclasses import dataclass

from kernel_domain.result import Result

from application.authorization import ProductAuthorizer
from application.errors import ProductNotFoundError
from application.ports import (
    Actor,
    IdentityGateway,
    ProductCommandPort,
)
from contracts.product import ProductView
from domain.product_id import ProductId


@dataclass(frozen=True)
class DeactivateProductCommand:
    """DTO для команды деактивации товара."""

    product_id: uuid.UUID
    actor: Actor


class DeactivateProductCommandHandler:
    """
    Business Logic Summary

    Context & Purpose: Деактивация товара, скрытие его из общего каталога.
    Validations: Проверка прав (владелец или админ).
    Side Effects: Статус товара в репозитории меняется на неактивный.
    """

    def __init__(
        self, repository: ProductCommandPort, identity: IdentityGateway
    ) -> None:
        self._repository = repository
        self._authorizer = ProductAuthorizer(identity)

    async def execute(self, command: DeactivateProductCommand) -> Result[ProductView]:
        product = await self._repository.get_by_id(ProductId(command.product_id))
        if product is None:
            raise ProductNotFoundError
        await self._authorizer.require_owner_or_admin(command.actor, product)
        result = await self._repository.deactivate(product.id)
        if result is None:
            raise ProductNotFoundError
        if result.is_err:
            return Result.fail(result.error)
        return Result.ok(ProductView.from_domain(result.value))
