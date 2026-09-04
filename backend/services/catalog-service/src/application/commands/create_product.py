# ruff: noqa: E501
"""Команда и handler create-product."""

from dataclasses import dataclass

from kernel_domain.result import Result

from application.ports import (
    Actor,
    IdentityGateway,
    OwnerReadModel,
    OwnerSnapshot,
)
from contracts.product import ProductView
from domain.unit_of_work import CatalogUnitOfWork


@dataclass(frozen=True)
class CreateProductCommand:
    """DTO для команды создания нового товара."""

    actor: Actor
    name: str
    description: str
    price: float
    category: str


class CreateProductCommandHandler:
    """
    Business Logic Summary

    Context & Purpose: Создание новой карточки товара в системе.
    Validations: Проверяет наличие владельца в ReadModel, если нет - создает снимок владельца.
    Side Effects: Добавляется новая запись товара в репозиторий, возможно сохраняется OwnerSnapshot.
    """

    def __init__(
        self,
        uow: CatalogUnitOfWork,
        owner_read_model: OwnerReadModel,
        identity: IdentityGateway,
    ) -> None:
        self._uow = uow
        self._owner_read_model = owner_read_model
        self._identity = identity

    async def execute(self, command: CreateProductCommand) -> Result[ProductView]:
        async with self._uow:
            if await self._owner_read_model.get(command.actor.user_id) is None:
                info = await self._identity.fetch_current_user(command.actor.token)
                await self._owner_read_model.upsert(
                    OwnerSnapshot(
                        user_id=info.id,
                        role=info.role,
                        is_active=info.is_active,
                        last_applied_outbox_id=0,
                    )
                )
            result = await self._uow.products.create(
                name=command.name,
                description=command.description,
                price=command.price,
                category=command.category,
                user_id=command.actor.user_id,
            )
            if result.is_err:
                return Result[ProductView].fail(result.error)
            await self._uow.commit()
        return Result[ProductView].ok(ProductView.from_domain(result.value))
