"""Реальный Redis (testcontainers) для TTL и границы scope кэша первой
страницы (issue #293 acceptance criteria 1-2) — юнит-тест
(`tests/unit/test_cached_product_search.py`) покрывает нормализацию ключа и
устойчивость к сбоям Redis фейком без настоящей TTL-семантики."""

import asyncio
import uuid

import pytest
from kernel_platform.pagination import Page, PageInfo

from application.search_cursor import ProductSortOption, SearchCursor
from contracts.product import ProductView
from infrastructure.search.cache import CachedProductSearch

pytestmark = pytest.mark.asyncio(loop_scope="session")

_PRODUCT = ProductView(
    id=uuid.UUID("00000000-0000-0000-0000-000000000001"),
    name="Cordless drill",
    description="18V brushless drill",
    price=99.0,
    category="Tools",
    user_id=uuid.UUID("00000000-0000-0000-0000-000000000002"),
    is_active=True,
)
_PAGE = Page(
    items=[_PRODUCT],
    page_info=PageInfo(
        next_cursor=None, prev_cursor=None, has_more=False, has_prev=False
    ),
)


class FakeProductSearch:
    def __init__(self) -> None:
        self.calls = 0

    async def search(
        self,
        query: str | None = None,
        *,
        category: str | None = None,
        min_price: float | None = None,
        max_price: float | None = None,
        sort: ProductSortOption | None = None,
        limit: int = 20,
        cursor: SearchCursor | None = None,
    ) -> Page[ProductView]:
        self.calls += 1
        return _PAGE


async def test_first_page_is_cached_with_exactly_the_configured_ttl(
    redis_client,
) -> None:
    inner = FakeProductSearch()
    cache = CachedProductSearch(inner, redis_client, ttl_seconds=2)

    await cache.search("drill")
    second = await cache.search("drill")

    assert second == _PAGE
    assert inner.calls == 1
    keys = await redis_client.keys("catalog:search:first-page:*")
    assert len(keys) == 1
    ttl = await redis_client.ttl(keys[0])
    assert 0 < ttl <= 2


async def test_cache_entry_expires_after_ttl_and_search_port_is_called_again(
    redis_client,
) -> None:
    inner = FakeProductSearch()
    cache = CachedProductSearch(inner, redis_client, ttl_seconds=1)

    await cache.search("drill")
    await asyncio.sleep(1.3)
    await cache.search("drill")

    assert inner.calls == 2


async def test_cursor_pages_never_read_or_write_redis(redis_client) -> None:
    inner = FakeProductSearch()
    cache = CachedProductSearch(inner, redis_client, ttl_seconds=60)
    cursor = SearchCursor(
        sort=ProductSortOption.RELEVANCE, sort_value=1.0, product_id=uuid.uuid4()
    )

    await cache.search("drill", cursor=cursor)
    await cache.search("drill", cursor=cursor)

    assert inner.calls == 2
    assert await redis_client.dbsize() == 0


async def test_a_cursor_request_does_not_share_the_first_page_cache_entry(
    redis_client,
) -> None:
    inner = FakeProductSearch()
    cache = CachedProductSearch(inner, redis_client, ttl_seconds=60)
    cursor = SearchCursor(
        sort=ProductSortOption.RELEVANCE, sort_value=1.0, product_id=uuid.uuid4()
    )

    await cache.search("drill")
    await cache.search("drill", cursor=cursor)
    await cache.search("drill")

    assert inner.calls == 2
