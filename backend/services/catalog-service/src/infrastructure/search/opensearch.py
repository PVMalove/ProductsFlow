import asyncio
import uuid
from datetime import UTC, datetime

import httpx
from kernel_platform.pagination import Page, PageInfo

from application.search_cursor import (
    ProductSortOption,
    SearchCursor,
    encode_search_cursor,
)
from application.search_snapshot import ProductSearchSnapshot, ProductSearchTombstone
from contracts.product import ProductView
from infrastructure.metrics.search_metrics import observe_opensearch_latency

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
        self._reindex_target: str | None = None
        self._rebuild_alias = f"{index_name}-rebuild"

    async def close(self) -> None:
        if self._owns_client:
            await self._client.aclose()

    async def search(
        self,
        query: str | None = None,
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

        bool_query: dict[str, object] = {"filter": filters}
        if query:
            bool_query["must"] = [
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
            ]

        body: dict[str, object] = {
            "size": limit + 1,
            "query": {"bool": bool_query},
            "sort": _SORT_CLAUSES[sort],
        }
        if cursor is not None:
            body["search_after"] = [cursor.sort_value, str(cursor.product_id)]

        async with observe_opensearch_latency("search"):
            response = await self._client.post(
                f"/{self._index_name}/_search", json=body
            )
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
        await self._write_snapshot(
            self._index_name, snapshot, owner_is_active=owner_is_active
        )
        # The rebuild alias makes mirroring visible to independently-running
        # worker processes too.  Outside a rebuild it simply resolves to 404.
        await self._write_snapshot(
            self._rebuild_alias,
            snapshot,
            owner_is_active=owner_is_active,
            ignore_missing=True,
        )

    async def index_rebuild(
        self, snapshot: ProductSearchSnapshot, *, owner_is_active: bool
    ) -> None:
        if self._reindex_target is None:
            raise RuntimeError("Search reindex has not been started")
        await self._write_snapshot(
            self._reindex_target, snapshot, owner_is_active=owner_is_active
        )

    async def begin_reindex(self) -> None:
        await self._ensure_index()
        if self._reindex_target is not None:
            raise RuntimeError("Search reindex is already running")
        target = f"{self._index_name}-v{datetime.now(UTC):%Y%m%d%H%M%S%f}"
        response = await self._client.put(
            f"/{target}",
            json={
                "settings": self._index_settings(),
                "mappings": {"properties": self._index_properties()},
            },
        )
        response.raise_for_status()
        mirror_alias_response = await self._client.post(
            "/_aliases",
            json={
                "actions": [{"add": {"index": target, "alias": self._rebuild_alias}}]
            },
        )
        mirror_alias_response.raise_for_status()
        self._reindex_target = target

    async def complete_reindex(self) -> None:
        target = self._reindex_target
        if target is None:
            raise RuntimeError("Search reindex has not been started")
        response = await self._client.post(
            "/_aliases",
            json={
                "actions": [
                    {"remove": {"index": "*", "alias": self._index_name}},
                    {"add": {"index": target, "alias": self._index_name}},
                    {"remove": {"index": target, "alias": self._rebuild_alias}},
                ]
            },
        )
        response.raise_for_status()
        self._reindex_target = None

    async def _write_snapshot(
        self,
        index_name: str,
        snapshot: ProductSearchSnapshot,
        *,
        owner_is_active: bool,
        ignore_missing: bool = False,
    ) -> None:
        async with observe_opensearch_latency("index"):
            response = await self._client.put(
                f"/{index_name}/_doc/{snapshot.product_id}",
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
        # A delayed snapshot must not retry forever after external versioning
        # rejected it: the newer document is already the desired state.
        if response.status_code not in ({404, 409} if ignore_missing else {409}):
            response.raise_for_status()

    async def delete(self, tombstone: ProductSearchTombstone) -> None:
        """Apply a versioned tombstone without retaining Product data.

        ``external_gte`` makes this operation idempotent and ensures a late
        deletion cannot erase a document written at a higher revision.
        """
        targets = [self._index_name, self._rebuild_alias]
        for index_name in targets:
            async with observe_opensearch_latency("delete"):
                response = await self._client.delete(
                    f"/{index_name}/_doc/{tombstone.product_id}",
                    params={
                        "version": tombstone.search_revision,
                        "version_type": "external_gte",
                    },
                )
            # 404 means this index never observed the Product.  409 is a stale
            # tombstone, which is likewise already superseded and must be acked.
            if response.status_code not in {404, 409}:
                response.raise_for_status()

    async def set_owner_active(self, user_id: uuid.UUID, *, is_active: bool) -> None:
        """Mass-updates every already-indexed Product of `user_id` in place,
        so an owner lifecycle event doesn't wait for each Product's own event
        to replay (issue #288 acceptance criterion 2)."""
        targets = [self._index_name, self._rebuild_alias]
        for index_name in targets:
            response = await self._client.post(
                f"/{index_name}/_update_by_query",
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
            if response.status_code != 404:
                response.raise_for_status()

    async def _ensure_index(self) -> None:
        if self._index_ready:
            return
        async with self._index_ready_lock:
            if self._index_ready:
                return
            concrete_index = f"{self._index_name}-v1"
            response = await self._client.put(
                f"/{concrete_index}",
                json={
                    "settings": self._index_settings(),
                    "mappings": {"properties": self._index_properties()},
                },
            )
            if response.status_code in {200, 201}:
                alias_response = await self._client.post(
                    "/_aliases",
                    json={
                        "actions": [
                            {
                                "add": {
                                    "index": concrete_index,
                                    "alias": self._index_name,
                                }
                            }
                        ]
                    },
                )
                alias_response.raise_for_status()
                self._index_ready = True
                return
            if response.status_code != 400:
                response.raise_for_status()
            error = response.json().get("error", {})
            if error.get("type") != "resource_already_exists_exception":
                response.raise_for_status()

            # A pre-alias legacy index continues to work as the read/write
            # target.  The first explicit rebuild moves it to versioned alias
            # topology without interrupting the existing search endpoint.
            mapping_response = await self._client.get(f"/{concrete_index}/_mapping")
            mapping_response.raise_for_status()
            if not self._has_current_mapping(mapping_response.json()):
                update_mapping_response = await self._client.put(
                    f"/{concrete_index}/_mapping",
                    json={"properties": self._index_properties()},
                )
                update_mapping_response.raise_for_status()
                reindex_response = await self._client.post(
                    f"/{concrete_index}/_update_by_query",
                    params={"conflicts": "proceed", "refresh": "true"},
                    json={"query": {"match_all": {}}},
                )
                reindex_response.raise_for_status()
            self._index_ready = True

    @staticmethod
    def _index_settings() -> dict[str, object]:
        return {
            "number_of_shards": 1,
            "number_of_replicas": 0,
            "analysis": {
                "normalizer": {"lowercase": {"type": "custom", "filter": ["lowercase"]}}
            },
        }

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
        index = payload.get(f"{self._index_name}-v1")
        if not isinstance(index, dict):
            # OpenSearch may return a concrete generation other than v1 when
            # an operator has already rebuilt this alias.
            index = next(
                (value for value in payload.values() if isinstance(value, dict)), None
            )
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
