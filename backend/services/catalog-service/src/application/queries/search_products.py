"""Public product search query."""

from dataclasses import dataclass

from kernel_domain.result import Result
from kernel_platform.pagination import DEFAULT_PAGE_LIMIT, Page

from application.ports import (
    ProductImageLookupPort,
    ProductImageUrlBuilder,
    ProductSearchPort,
)
from application.queries.attach_image_urls import attach_image_urls
from application.search_cursor import (
    ProductSortOption,
    SearchCursor,
    resolve_search_sort,
)
from contracts.product import ProductView


@dataclass(frozen=True)
class SearchProductsQuery:
    q: str | None = None
    category: str | None = None
    min_price: float | None = None
    max_price: float | None = None
    sort: ProductSortOption | None = None
    limit: int = DEFAULT_PAGE_LIMIT
    cursor: SearchCursor | None = None


class SearchProductsQueryHandler:
    """Returns public active Product matches from the search read model."""

    def __init__(
        self,
        search: ProductSearchPort,
        repository: ProductImageLookupPort,
        storage: ProductImageUrlBuilder,
        bucket_name: str,
    ) -> None:
        self._search = search
        self._repository = repository
        self._storage = storage
        self._bucket_name = bucket_name

    async def execute(self, query: SearchProductsQuery) -> Result[Page[ProductView]]:
        sort = resolve_search_sort(query.q, query.sort)
        page = await self._search.search(
            query.q,
            category=query.category,
            min_price=query.min_price,
            max_price=query.max_price,
            sort=sort,
            limit=query.limit,
            cursor=query.cursor,
        )
        items = await attach_image_urls(
            page.items,
            repository=self._repository,
            storage=self._storage,
            bucket_name=self._bucket_name,
        )
        return Result[Page[ProductView]].ok(Page(items=items, page_info=page.page_info))
