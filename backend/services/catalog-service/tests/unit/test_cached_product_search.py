import uuid

import pytest
from kernel_platform.pagination import Page, PageInfo

from application.search_cursor import ProductSortOption, SearchCursor
from contracts.product import ProductView
from infrastructure.metrics.search_metrics import SEARCH_CACHE_REQUESTS
from infrastructure.search.cache import CachedProductSearch

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
    def __init__(self, page: Page[ProductView] = _PAGE) -> None:
        self.calls: list[dict[str, object]] = []
        self._page = page

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
        self.calls.append(
            {
                "query": query,
                "category": category,
                "min_price": min_price,
                "max_price": max_price,
                "sort": sort,
                "limit": limit,
                "cursor": cursor,
            }
        )
        return self._page


class FakeRedis:
    """Соответствует `RedisLike` — минимальный in-memory дублёр без TTL-семантики
    (реальную протухаемость по TTL проверяет integration-тест с настоящим Redis)."""

    def __init__(self) -> None:
        self.store: dict[str, str] = {}
        self.set_calls: list[tuple[str, str, int]] = []
        self.get_calls: list[str] = []

    async def get(self, name: str) -> str | None:
        self.get_calls.append(name)
        return self.store.get(name)

    async def set(self, name: str, value: str, *, ex: int) -> object:
        self.set_calls.append((name, value, ex))
        self.store[name] = value
        return True


def _metric_value(*, result: str) -> float:
    for metric in SEARCH_CACHE_REQUESTS.collect():
        for sample in metric.samples:
            if sample.name.endswith("_total") and sample.labels.get("result") == result:
                return sample.value
    return 0.0


async def test_first_call_misses_and_populates_cache_with_configured_ttl() -> None:
    inner = FakeProductSearch()
    redis = FakeRedis()
    cache = CachedProductSearch(inner, redis, ttl_seconds=60)
    miss_before, hit_before = _metric_value(result="miss"), _metric_value(result="hit")

    page = await cache.search("drill")

    assert page == _PAGE
    assert len(inner.calls) == 1
    assert len(redis.set_calls) == 1
    _, _, ttl = redis.set_calls[0]
    assert ttl == 60
    assert _metric_value(result="miss") == miss_before + 1
    assert _metric_value(result="hit") == hit_before


async def test_second_identical_call_is_served_from_cache_not_search_port() -> None:
    inner = FakeProductSearch()
    redis = FakeRedis()
    cache = CachedProductSearch(inner, redis, ttl_seconds=60)
    miss_before, hit_before = _metric_value(result="miss"), _metric_value(result="hit")

    first = await cache.search("drill", category="Tools", limit=10)
    second = await cache.search("drill", category="Tools", limit=10)

    assert second == first
    assert len(inner.calls) == 1
    assert _metric_value(result="hit") == hit_before + 1
    assert _metric_value(result="miss") == miss_before + 1


async def test_cache_key_normalizes_query_and_category_case_and_whitespace() -> None:
    inner = FakeProductSearch()
    redis = FakeRedis()
    cache = CachedProductSearch(inner, redis, ttl_seconds=60)

    await cache.search(" Drill ", category="TOOLS")
    await cache.search("drill", category="tools")

    assert len(inner.calls) == 1


async def test_catalog_without_query_is_cached_and_defaults_to_newest() -> None:
    inner = FakeProductSearch()
    redis = FakeRedis()
    cache = CachedProductSearch(inner, redis, ttl_seconds=60)

    first = await cache.search()
    second = await cache.search()

    assert second == first
    assert inner.calls == [
        {
            "query": None,
            "category": None,
            "min_price": None,
            "max_price": None,
            "sort": ProductSortOption.NEWEST,
            "limit": 20,
            "cursor": None,
        }
    ]


@pytest.mark.parametrize(
    "kwargs",
    [
        {"category": "Electronics"},
        {"min_price": 10.0},
        {"max_price": 99.0},
        {"sort": ProductSortOption.PRICE_ASC},
        {"limit": 5},
    ],
)
async def test_cache_key_distinguishes_each_filter_sort_and_limit_dimension(
    kwargs: dict[str, object],
) -> None:
    inner = FakeProductSearch()
    redis = FakeRedis()
    cache = CachedProductSearch(inner, redis, ttl_seconds=60)

    await cache.search("drill")
    await cache.search("drill", **kwargs)  # type: ignore[arg-type]

    assert len(inner.calls) == 2


async def test_cursor_pages_are_never_cached() -> None:
    inner = FakeProductSearch()
    redis = FakeRedis()
    cache = CachedProductSearch(inner, redis, ttl_seconds=60)
    cursor = SearchCursor(
        sort=ProductSortOption.RELEVANCE, sort_value=1.0, product_id=uuid.uuid4()
    )
    miss_before, hit_before = _metric_value(result="miss"), _metric_value(result="hit")

    await cache.search("drill", cursor=cursor)
    await cache.search("drill", cursor=cursor)

    assert len(inner.calls) == 2
    assert redis.store == {}
    assert _metric_value(result="hit") == hit_before
    assert _metric_value(result="miss") == miss_before


async def test_a_cursor_request_does_not_read_or_populate_the_first_page_entry() -> (
    None
):
    inner = FakeProductSearch()
    redis = FakeRedis()
    cache = CachedProductSearch(inner, redis, ttl_seconds=60)
    cursor = SearchCursor(
        sort=ProductSortOption.RELEVANCE, sort_value=1.0, product_id=uuid.uuid4()
    )
    miss_before = _metric_value(result="miss")

    await cache.search("drill", cursor=cursor)
    await cache.search("drill")

    assert len(inner.calls) == 2
    assert _metric_value(result="miss") == miss_before + 1


async def test_redis_get_failure_is_treated_as_a_miss_and_search_still_succeeds() -> (
    None
):
    inner = FakeProductSearch()

    class BrokenRedis(FakeRedis):
        async def get(self, name: str) -> str | None:
            raise ConnectionError("redis unavailable")

    cache = CachedProductSearch(inner, BrokenRedis(), ttl_seconds=60)

    page = await cache.search("drill")

    assert page == _PAGE
    assert len(inner.calls) == 1


async def test_redis_set_failure_does_not_break_search() -> None:
    inner = FakeProductSearch()

    class BrokenRedis(FakeRedis):
        async def set(self, name: str, value: str, *, ex: int) -> object:
            raise ConnectionError("redis unavailable")

    cache = CachedProductSearch(inner, BrokenRedis(), ttl_seconds=60)

    page = await cache.search("drill")

    assert page == _PAGE


async def test_corrupted_cache_entry_is_treated_as_a_miss() -> None:
    inner = FakeProductSearch()
    redis = FakeRedis()
    cache = CachedProductSearch(inner, redis, ttl_seconds=60)
    await cache.search("drill")
    key = next(iter(redis.store))
    redis.store[key] = "not-json"

    page = await cache.search("drill")

    assert page == _PAGE
    assert len(inner.calls) == 2
