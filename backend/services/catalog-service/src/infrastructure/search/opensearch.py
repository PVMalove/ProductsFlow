import asyncio
import uuid

import httpx
from kernel_platform.pagination import Page, PageInfo

from application.search_cursor import (
    ProductSortOption,
    SearchCursor,
    encode_search_cursor,
)
from application.search_snapshot import ProductSearchSnapshot
from contracts.product import ProductView

_SORT_CLAUSES: dict[ProductSortOption, list[dict[str, str]]] = {
    ProductSortOption.RELEVANCE: [{"_score": "desc"}, {"id": "asc"}],
    ProductSortOption.PRICE_ASC: [{"price": "asc"}, {"id": "asc"}],
    ProductSortOption.PRICE_DESC: [{"price": "desc"}, {"id": "asc"}],
    ProductSortOption.NEWEST: [{"created_at": "desc"}, {"id": "asc"}],
}


class OpenSearchProductSearch:
    """Thin OpenSearch adapter for the public Product read model."""

    def __init__(
        self,
        *,
        base_url: str,
        index_name: str,
        client: httpx.AsyncClient | None = None,
    ) -> None:
        self._client = client or httpx.AsyncClient(base_url=base_url)
        self._owns_client = client is None
        self._index_name = index_name
        self._index_ready = False
        self._index_ready_lock = asyncio.Lock()

    async def close(self) -> None:
        if self._owns_client:
            await self._client.aclose()

    async def search(
        self,
        query: str,
        *,
        category: str | None = None,
        min_price: float | None = None,
        max_price: float | None = None,
        sort: ProductSortOption = ProductSortOption.RELEVANCE,
        limit: int = 20,
        cursor: SearchCursor | None = None,
    ) -> Page[ProductView]:
        filters: list[dict[str, object]] = [
            {"term": {"is_active": True}},
            {"term": {"owner_is_active": True}},
        ]
        if category is not None:
            filters.append({"term": {"category": category}})
        if min_price is not None or max_price is not None:
            price_range: dict[str, float] = {}
            if min_price is not None:
                price_range["gte"] = min_price
            if max_price is not None:
                price_range["lte"] = max_price
            filters.append({"range": {"price": price_range}})

        body: dict[str, object] = {
            "size": limit + 1,
            "query": {
                "bool": {
                    "filter": filters,
                    "must": [
                        {
                            "multi_match": {
                                "query": query,
                                "fields": [
                                    "name.ru^3",
                                    "name.en^3",
                                    "description.ru",
                                    "description.en",
                                ],
                                "fuzziness": "AUTO",
                            }
                        }
                    ],
                }
            },
            "sort": _SORT_CLAUSES[sort],
        }
        if cursor is not None:
            body["search_after"] = [cursor.sort_value, str(cursor.product_id)]

        response = await self._client.post(f"/{self._index_name}/_search", json=body)
        if response.status_code == 404:
            return Page(
                items=[],
                page_info=PageInfo(
                    next_cursor=None, prev_cursor=None, has_more=False, has_prev=False
                ),
            )
        response.raise_for_status()
        hits = response.json()["hits"]["hits"]
        has_more = len(hits) > limit
        page_hits = hits[:limit]
        items = [self._to_view(hit["_source"]) for hit in page_hits]

        next_cursor = None
        if has_more and page_hits:
            sort_values = page_hits[-1]["sort"]
            next_cursor = encode_search_cursor(
                SearchCursor(
                    sort=sort,
                    sort_value=float(sort_values[0]),
                    product_id=uuid.UUID(str(sort_values[1])),
                )
            )
        return Page(
            items=items,
            page_info=PageInfo(
                next_cursor=next_cursor,
                prev_cursor=None,
                has_more=has_more,
                has_prev=False,
            ),
        )

    async def index(
        self, snapshot: ProductSearchSnapshot, *, owner_is_active: bool
    ) -> None:
        await self._ensure_index()
        response = await self._client.put(
            f"/{self._index_name}/_doc/{snapshot.product_id}",
            params={
                "version": snapshot.search_revision,
                "version_type": "external_gte",
            },
            json={
                "id": str(snapshot.product_id),
                "user_id": str(snapshot.user_id),
                "name": snapshot.name,
                "description": snapshot.description,
                "category": snapshot.category,
                "price": snapshot.price,
                "is_active": snapshot.is_active,
                "owner_is_active": owner_is_active,
                "created_at": snapshot.created_at.isoformat(),
            },
        )
        response.raise_for_status()

    async def set_owner_active(self, user_id: uuid.UUID, *, is_active: bool) -> None:
        """Mass-updates every already-indexed Product of `user_id` in place,
        so an owner lifecycle event doesn't wait for each Product's own event
        to replay (issue #288 acceptance criterion 2)."""
        response = await self._client.post(
            f"/{self._index_name}/_update_by_query",
            params={"conflicts": "proceed"},
            json={
                "query": {"term": {"user_id": str(user_id)}},
                "script": {
                    "source": "ctx._source.owner_is_active = params.is_active",
                    "lang": "painless",
                    "params": {"is_active": is_active},
                },
            },
        )
        if response.status_code == 404:
            return
        response.raise_for_status()

    async def _ensure_index(self) -> None:
        if self._index_ready:
            return
        async with self._index_ready_lock:
            if self._index_ready:
                return
            response = await self._client.put(
                f"/{self._index_name}",
                json={
                    "settings": {
                        "number_of_shards": 1,
                        "number_of_replicas": 0,
                        "analysis": {
                            "normalizer": {
                                "lowercase": {"type": "custom", "filter": ["lowercase"]}
                            }
                        },
                    },
                    "mappings": {"properties": self._index_properties()},
                },
            )
            if response.status_code == 200:
                self._index_ready = True
                return
            if response.status_code != 400:
                response.raise_for_status()
            error = response.json().get("error", {})
            if error.get("type") != "resource_already_exists_exception":
                response.raise_for_status()

            mapping_response = await self._client.get(f"/{self._index_name}/_mapping")
            mapping_response.raise_for_status()
            if not self._has_current_mapping(mapping_response.json()):
                update_mapping_response = await self._client.put(
                    f"/{self._index_name}/_mapping",
                    json={"properties": self._index_properties()},
                )
                update_mapping_response.raise_for_status()
                reindex_response = await self._client.post(
                    f"/{self._index_name}/_update_by_query",
                    params={"conflicts": "proceed", "refresh": "true"},
                    json={"query": {"match_all": {}}},
                )
                reindex_response.raise_for_status()
            self._index_ready = True

    @staticmethod
    def _multilingual_properties() -> dict[str, object]:
        return {
            field: {
                "type": "text",
                "fields": {
                    "ru": {"type": "text", "analyzer": "russian"},
                    "en": {"type": "text", "analyzer": "english"},
                },
            }
            for field in ("name", "description")
        }

    @staticmethod
    def _index_properties() -> dict[str, object]:
        return {
            **OpenSearchProductSearch._multilingual_properties(),
            "id": {"type": "keyword"},
            "category": {"type": "keyword", "normalizer": "lowercase"},
            "price": {"type": "double"},
            "created_at": {"type": "date"},
        }

    def _has_current_mapping(self, payload: dict[str, object]) -> bool:
        index = payload.get(self._index_name)
        if not isinstance(index, dict):
            return False
        mappings = index.get("mappings")
        if not isinstance(mappings, dict):
            return False
        properties = mappings.get("properties")
        if not isinstance(properties, dict):
            return False
        return self._has_multilingual_properties(properties) and all(
            properties.get(field) == expected
            for field, expected in (
                ("id", {"type": "keyword"}),
                ("category", {"type": "keyword", "normalizer": "lowercase"}),
                ("price", {"type": "double"}),
                ("created_at", {"type": "date"}),
            )
        )

    @staticmethod
    def _has_multilingual_properties(properties: dict[str, object]) -> bool:
        for field in ("name", "description"):
            definition = properties.get(field)
            if not isinstance(definition, dict):
                return False
            subfields = definition.get("fields")
            if not isinstance(subfields, dict) or not {"ru", "en"} <= subfields.keys():
                return False
        return True

    @staticmethod
    def _to_view(source: dict[str, object]) -> ProductView:
        price = source["price"]
        if isinstance(price, bool) or not isinstance(price, (int, float)):
            raise ValueError("OpenSearch product source has invalid price")
        return ProductView(
            id=uuid.UUID(str(source["id"])),
            name=str(source["name"]),
            description=str(source["description"]),
            price=float(price),
            category=str(source["category"]),
            user_id=uuid.UUID(str(source["user_id"])),
            is_active=bool(source["is_active"]),
        )
