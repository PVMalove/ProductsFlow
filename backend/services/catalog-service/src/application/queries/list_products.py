# ruff: noqa: E501
"""Query и handler для списка товаров."""

from dataclasses import dataclass

from kernel_domain.result import Result
from kernel_platform.pagination import Page

from application.ports import ProductImageUrlBuilder, ProductQueryPort
from application.queries.attach_image_urls import attach_image_urls
from contracts.product import ProductView
from domain.repositories import CatalogListCursor, ProductListSortOption


@dataclass(frozen=True)
class ListProductsQuery:
    """DTO для списка товаров (пагинация)."""

    limit: int
    after: CatalogListCursor | None = None
    before: CatalogListCursor | None = None
    category: str | None = None
    min_price: float | None = None
    max_price: float | None = None
    sort: ProductListSortOption = ProductListSortOption.NEWEST


class ListProductsQueryHandler:
    """
    Business Logic Summary

    Context & Purpose: Получение списка товаров (ленты) с поддержкой курсорной пагинации.
    Validations: Специфичных нет.
    Data Sourcing: ProductQueryPort, фильтрация по курсорам (after/before); элементы
    маппятся в transport-neutral ProductView, страница — в Page (ADR 0002, issue #221).
    """

    def __init__(
        self,
        repository: ProductQueryPort,
        storage: ProductImageUrlBuilder,
        bucket_name: str,
    ) -> None:
        self._repository = repository
        self._storage = storage
        self._bucket_name = bucket_name

    async def execute(self, query: ListProductsQuery) -> Result[Page[ProductView]]:
        page = await self._repository.list(
            limit=query.limit,
            after=query.after,
            before=query.before,
            category=query.category,
            min_price=query.min_price,
            max_price=query.max_price,
            sort=query.sort,
        )
        items = [ProductView.from_domain(item) for item in page.items]
        items = await attach_image_urls(
            items,
            repository=self._repository,
            storage=self._storage,
            bucket_name=self._bucket_name,
        )
        return Result[Page[ProductView]].ok(Page(items=items, page_info=page.page_info))
