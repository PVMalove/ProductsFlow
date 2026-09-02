# ruff: noqa: E501
"""Get-product query and visibility handler."""

import uuid
from dataclasses import dataclass

from application.authorization import ProductAuthorizer
from application.errors import ProductNotFoundError
from application.ports import (
    Actor,
    IdentityGateway,
    OwnerQueryPort,
    ProductQueryPort,
)
from domain.product import Product
from domain.product_id import ProductId
from domain.viewer import Viewer
from domain.visibility import ProductVisibilityPolicy


@dataclass(frozen=True)
class GetProductQuery:
    """DTO для запроса получения товара по ID."""

    """
    DTO для получения товара.
    
    Атрибуты:
        product_id: Уникальный идентификатор товара.
        actor: Пользователь, выполняющий запрос, или None для анонимного доступа.
    """
    product_id: uuid.UUID
    actor: Actor | None


class GetProductQueryHandler:
    """
    Business Logic Summary

    Context & Purpose: Чтение детальной информации о товаре.
    Validations: Проверяет политику видимости (активен ли товар и владелец, либо является ли актор админом/владельцем).
    Data Sourcing: Данные извлекаются из ProductQueryPort.
    """

    """
    Business Logic Summary
    
    Context & Purpose: Получение товара по его идентификатору с учетом прав доступа и видимости.
    Validations: Проверяет существование товара. Проверяет права доступа: товар доступен его владельцу (всегда), администратору (всегда) или любому пользователю, если владелец активен и товар отвечает правилам видимости (ProductVisibilityPolicy).
    Data Sourcing: Данные товара загружаются из ProductQueryPort. Дополнительно проверяется статус владельца через OwnerQueryPort и права администратора через IdentityGateway.
    """

    def __init__(
        self,
        repository: ProductQueryPort,
        owner_read_model: OwnerQueryPort,
        identity: IdentityGateway,
    ) -> None:
        self._repository = repository
        self._owner_read_model = owner_read_model
        self._authorizer = ProductAuthorizer(identity)
        self._visibility = ProductVisibilityPolicy()

    async def execute(self, query: GetProductQuery) -> Product:
        """
        Выполняет запрос на получение товара.

        @param query — DTO запроса (GetProductQuery), содержащий ID товара и информацию о пользователе.
        @return — Найденная сущность товара (Product).
        @raises ProductNotFoundError — если товар не найден или недоступен для текущего пользователя.
        """
        product = await self._repository.get_by_id(ProductId(query.product_id))
        if product is None:
            raise ProductNotFoundError

        if query.actor is not None and query.actor.user_id == product.user_id:
            return product

        owner = await self._owner_read_model.get(product.user_id)
        viewer = Viewer(
            user_id=query.actor.user_id if query.actor is not None else None,
            is_admin=False,
        )
        if (
            owner is not None
            and owner.is_active
            and self._visibility.is_visible(viewer, product)
        ):
            return product

        if query.actor is not None and await self._authorizer.is_admin(query.actor):
            return product
        raise ProductNotFoundError
