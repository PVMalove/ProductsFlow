# ruff: noqa: E501
"""Query и handler для списка товаров."""

from dataclasses import dataclass

from kernel_domain.result import Result
from kernel_platform.pagination import Page

from application.ports import ProductQueryPort
from contracts.product import ProductView
from domain.repositories import Cursor


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
    Data Sourcing: ProductQueryPort, фильтрация по курсорам (after/before); элементы
    маппятся в transport-neutral ProductView, страница — в Page (ADR 0002, issue #221).
    """

    def __init__(self, repository: ProductQueryPort) -> None:
        self._repository = repository

    async def execute(self, query: ListProductsQuery) -> Result[Page[ProductView]]:
        page = await self._repository.list(
            limit=query.limit, after=query.after, before=query.before
        )
        items = [ProductView.from_domain(item) for item in page.items]
        return Result[Page[ProductView]].ok(Page(items=items, page_info=page.page_info))
