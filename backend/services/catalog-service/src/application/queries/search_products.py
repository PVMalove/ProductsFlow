"""Public product search query."""

from dataclasses import dataclass

from kernel_domain.result import Result
from kernel_platform.pagination import DEFAULT_PAGE_LIMIT, Page

from application.ports import ProductSearchPort
from application.search_cursor import ProductSortOption, SearchCursor
from contracts.product import ProductView


@dataclass(frozen=True)
class SearchProductsQuery:
    q: str
    category: str | None = None
    min_price: float | None = None
    max_price: float | None = None
    sort: ProductSortOption = ProductSortOption.RELEVANCE
    limit: int = DEFAULT_PAGE_LIMIT
    cursor: SearchCursor | None = None


class SearchProductsQueryHandler:
    """Returns public active Product matches from the search read model."""

    def __init__(self, search: ProductSearchPort) -> None:
        self._search = search

    async def execute(self, query: SearchProductsQuery) -> Result[Page[ProductView]]:
        page = await self._search.search(
            query.q,
            category=query.category,
            min_price=query.min_price,
            max_price=query.max_price,
            sort=query.sort,
            limit=query.limit,
            cursor=query.cursor,
        )
        return Result[Page[ProductView]].ok(page)
