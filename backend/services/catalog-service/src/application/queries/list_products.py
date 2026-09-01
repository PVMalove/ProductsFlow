"""List-products query and handler."""

from dataclasses import dataclass

from application.ports import ProductQueryPort
from domain.repositories import Cursor, ProductPage


@dataclass(frozen=True)
class ListProductsQuery:
    limit: int
    after: Cursor | None = None
    before: Cursor | None = None


class ListProductsQueryHandler:
    def __init__(self, repository: ProductQueryPort) -> None:
        self._repository = repository

    async def handle(self, query: ListProductsQuery) -> ProductPage:
        return await self._repository.list(
            limit=query.limit, after=query.after, before=query.before
        )

    async def execute(
        self,
        *,
        limit: int,
        after: Cursor | None,
        before: Cursor | None,
    ) -> ProductPage:
        return await self.handle(
            ListProductsQuery(limit=limit, after=after, before=before)
        )
