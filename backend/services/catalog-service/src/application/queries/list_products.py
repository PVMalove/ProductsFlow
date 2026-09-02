# ruff: noqa: E501
"""List-products query and handler."""

from dataclasses import dataclass

from application.ports import ProductQueryPort
from domain.repositories import Cursor, ProductPage


@dataclass(frozen=True)
class ListProductsQuery:
    """DTO для списка товаров (пагинация)."""

    limit: int
    after: Cursor | None = None
    before: Cursor | None = None


class ListProductsQueryHandler:
    """
    Business Logic Summary

    Context & Purpose: Получение списка товаров (ленты) с поддержкой курсорной пагинации.
    Validations: Специфичных нет.
    Data Sourcing: ProductQueryPort, фильтрация по курсорам (after/before).
    """

    def __init__(self, repository: ProductQueryPort) -> None:
        self._repository = repository

    async def execute(self, query: ListProductsQuery) -> ProductPage:
        return await self._repository.list(
            limit=query.limit, after=query.after, before=query.before
        )
