# ruff: noqa: E501
"""Redis-кэш первой страницы публичного поиска (issue #293).

Кэшируется только страница без курсора: `q`/`category`/`min_price`/
`max_price`/`sort`/`limit` целиком определяют ключ, а курсорные страницы
всегда идут напрямую в OpenSearch (acceptance criterion 1) — так дешёвый
повторный публичный трафик по популярным первым страницам не долбит
OpenSearch, а листание вглубь результата остаётся всегда свежим. Протухание
только по TTL (`Settings.catalog_search_cache_ttl_seconds`, ровно 60с) — это
и есть контракт свежести, сложная адресная инвалидация по Product-мутациям
не нужна (acceptance criterion 2, epic #283)."""

import hashlib
import json
import logging
import uuid
from collections.abc import Awaitable
from dataclasses import asdict
from typing import Protocol

from kernel_platform.pagination import Page, PageInfo

from application.ports import ProductSearchPort
from application.search_cursor import (
    ProductSortOption,
    SearchCursor,
    resolve_search_sort,
)
from contracts.product import ProductView
from infrastructure.metrics.search_metrics import SEARCH_CACHE_REQUESTS

logger = logging.getLogger(__name__)

_CACHE_KEY_PREFIX = "catalog:search:first-page:"


class RedisLike(Protocol):
    """Единственная часть `redis.asyncio.Redis`, которая здесь нужна —
    отдельный протокол упрощает подмену фейком в юнит-тестах. Возвращаемый
    тип `get` включает `bytes`, т.к. стаб `redis.asyncio.Redis` не параметризует
    его по `decode_responses` — сам байтстринг декодируется в `_get`."""

    def get(self, name: str) -> Awaitable[str | bytes | None]: ...

    def set(self, name: str, value: str, *, ex: int) -> Awaitable[object]: ...


def _cache_key(
    query: str | None,
    *,
    category: str | None,
    min_price: float | None,
    max_price: float | None,
    sort: ProductSortOption,
    limit: int,
) -> str:
    """`query`/`category` нормализуются (trim + casefold) перед хэшированием,
    чтобы регистр и пробелы на границах не плодили отдельные записи кэша для
    результата, который OpenSearch и так вернёт идентичным (`category` в
    индексе матчится через `normalizer: lowercase`, см. `opensearch.py`)."""
    canonical = json.dumps(
        [
            query.strip().casefold() if query is not None else None,
            category.strip().casefold() if category is not None else None,
            min_price,
            max_price,
            sort.value,
            limit,
        ],
        separators=(",", ":"),
    )
    digest = hashlib.sha256(canonical.encode("utf-8")).hexdigest()
    return f"{_CACHE_KEY_PREFIX}{digest}"


def _encode_page(page: Page[ProductView]) -> str:
    items = [
        {**asdict(item), "id": str(item.id), "user_id": str(item.user_id)}
        for item in page.items
    ]
    return json.dumps({"items": items, "page_info": asdict(page.page_info)})


def _decode_page(raw: str) -> Page[ProductView]:
    payload = json.loads(raw)
    items = [
        ProductView(
            id=uuid.UUID(item["id"]),
            name=item["name"],
            description=item["description"],
            price=item["price"],
            category=item["category"],
            user_id=uuid.UUID(item["user_id"]),
            is_active=item["is_active"],
        )
        for item in payload["items"]
    ]
    return Page(items=items, page_info=PageInfo(**payload["page_info"]))


class CachedProductSearch:
    """`ProductSearchPort`, оборачивающий другой `ProductSearchPort`
    Redis-кэшем первой страницы."""

    def __init__(
        self, inner: ProductSearchPort, redis_client: RedisLike, *, ttl_seconds: int
    ) -> None:
        self._inner = inner
        self._redis = redis_client
        self._ttl_seconds = ttl_seconds

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
        resolved_sort = resolve_search_sort(query, sort)
        if cursor is not None:
            return await self._search_inner(
                query,
                category=category,
                min_price=min_price,
                max_price=max_price,
                sort=resolved_sort,
                limit=limit,
                cursor=cursor,
            )

        key = _cache_key(
            query,
            category=category,
            min_price=min_price,
            max_price=max_price,
            sort=resolved_sort,
            limit=limit,
        )
        cached = await self._get(key)
        if cached is not None:
            SEARCH_CACHE_REQUESTS.labels(result="hit").inc()
            return cached

        SEARCH_CACHE_REQUESTS.labels(result="miss").inc()
        page = await self._search_inner(
            query,
            category=category,
            min_price=min_price,
            max_price=max_price,
            sort=resolved_sort,
            limit=limit,
            cursor=None,
        )
        await self._set(key, page)
        return page

    async def _search_inner(
        self,
        query: str | None,
        *,
        category: str | None,
        min_price: float | None,
        max_price: float | None,
        sort: ProductSortOption,
        limit: int,
        cursor: SearchCursor | None,
    ) -> Page[ProductView]:
        return await self._inner.search(
            query,
            category=category,
            min_price=min_price,
            max_price=max_price,
            sort=sort,
            limit=limit,
            cursor=cursor,
        )

    async def _get(self, key: str) -> Page[ProductView] | None:
        try:
            raw = await self._redis.get(key)
        except Exception:
            logger.warning(
                "catalog-search cache: Redis GET упал, считаем промахом",
                exc_info=True,
            )
            return None
        if raw is None:
            return None
        if isinstance(raw, bytes):
            raw = raw.decode("utf-8")
        try:
            return _decode_page(raw)
        except (
            KeyError,
            TypeError,
            ValueError,
            json.JSONDecodeError,
        ):
            logger.warning(
                "catalog-search cache: повреждённая запись кэша, считаем промахом",
                exc_info=True,
            )
            return None

    async def _set(self, key: str, page: Page[ProductView]) -> None:
        try:
            await self._redis.set(key, _encode_page(page), ex=self._ttl_seconds)
        except Exception:
            logger.warning(
                "catalog-search cache: Redis SET упал, кэш не записан",
                exc_info=True,
            )
