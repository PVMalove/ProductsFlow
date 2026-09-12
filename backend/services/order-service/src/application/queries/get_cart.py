# ruff: noqa: E501
"""Query и handler чтения собственной корзины (issue #369)."""

import uuid
from dataclasses import dataclass

from kernel_domain.result import Result

from contracts.cart import CartView
from domain.repositories import CartRepository


@dataclass(frozen=True)
class GetCartQuery:
    user_id: uuid.UUID


class GetCartQueryHandler:
    """
    Business Logic Summary

    Context & Purpose: Чтение собственной корзины вызывающего.
    Validations: Нет — чистое чтение.
    Data Sourcing: CartRepository.get_for_user — без побочного эффекта записи; корзина без строки в БД возвращает пустой CartView (D3).
    """

    def __init__(self, repository: CartRepository) -> None:
        self._repository = repository

    async def execute(self, query: GetCartQuery) -> Result[CartView]:
        cart = await self._repository.get_for_user(query.user_id)
        if cart is None:
            return Result[CartView].ok(CartView.empty())
        return Result[CartView].ok(CartView.from_domain(cart))
