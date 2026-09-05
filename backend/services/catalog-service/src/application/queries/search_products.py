"""Public product search query."""

from dataclasses import dataclass

from kernel_domain.result import Result

from application.ports import ProductSearchPort
from contracts.product import ProductView


@dataclass(frozen=True)
class SearchProductsQuery:
    q: str


class SearchProductsQueryHandler:
    """Returns public active Product matches from the search read model."""

    def __init__(self, search: ProductSearchPort) -> None:
        self._search = search

    async def execute(self, query: SearchProductsQuery) -> Result[list[ProductView]]:
        return Result[list[ProductView]].ok(await self._search.search(query.q))
