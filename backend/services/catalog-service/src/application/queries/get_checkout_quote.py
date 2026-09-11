"""Query и handler авторитетного Checkout Quote (issue #366)."""

import uuid
from dataclasses import dataclass

from kernel_domain.result import Result

from application.errors import (
    CheckoutQuoteProductHiddenError,
    CheckoutQuoteProductInactiveError,
    CheckoutQuoteProductNotFoundError,
)
from application.ports import Actor, OwnerQueryPort, ProductQueryPort
from contracts.checkout_quote import CheckoutQuoteView
from domain.checkout_eligibility import evaluate_checkout_eligibility
from domain.errors import CatalogErrors
from domain.value_objects.product_id import ProductId


@dataclass(frozen=True)
class GetCheckoutQuoteQuery:
    """DTO для запроса авторитетного checkout quote.

    Атрибуты:
        product_id: Идентификатор товара.
        quantity: Запрошенное количество (должно быть положительным целым).
        actor: Аутентифицированный вызывающий — обязателен (`RequiredAuth`).
    """

    product_id: uuid.UUID
    quantity: int
    actor: Actor


class GetCheckoutQuoteQueryHandler:
    """
    Business Logic Summary

    Context & Purpose: Синхронный read-only Checkout Quote для будущего
    order-service — авторитетная цена/описание товара без доверия клиенту.
    Validations: `quantity` — положительное целое (Result-ошибка); товар
    существует (иначе NotFound); checkout eligibility (`evaluate_checkout_eligibility`)
    — строже видимости: даже владелец/админ не получает quote на
    деактивированный товар, поэтому `IdentityGateway`/admin-bypass не используются.
    Data Sourcing: ProductQueryPort + OwnerQueryPort.
    """

    def __init__(
        self,
        repository: ProductQueryPort,
        owner_read_model: OwnerQueryPort,
    ) -> None:
        self._repository = repository
        self._owner_read_model = owner_read_model

    async def execute(
        self, query: GetCheckoutQuoteQuery
    ) -> Result[CheckoutQuoteView]:
        """
        Выполняет запрос на получение checkout quote.

        @param query — DTO запроса (GetCheckoutQuoteQuery).
        @return — Транспортно-независимый контракт quote (Result[CheckoutQuoteView]).
        @raises CheckoutQuoteProductNotFoundError — если товар не найден или был удалён.
        @raises CheckoutQuoteProductHiddenError — если владелец товара деактивирован.
        @raises CheckoutQuoteProductInactiveError — если сам товар деактивирован.
        """
        if query.quantity <= 0:
            return Result[CheckoutQuoteView].fail(CatalogErrors.invalid_quantity())

        product = await self._repository.get_by_id(ProductId.create(query.product_id))
        if product is None:
            raise CheckoutQuoteProductNotFoundError

        owner = await self._owner_read_model.get(product.user_id)
        owner_is_active = owner is not None and owner.is_active

        error = evaluate_checkout_eligibility(product, owner_is_active=owner_is_active)
        if error is not None:
            if not owner_is_active:
                raise CheckoutQuoteProductHiddenError
            raise CheckoutQuoteProductInactiveError

        return Result[CheckoutQuoteView].ok(
            CheckoutQuoteView.from_domain(product, query.quantity)
        )
