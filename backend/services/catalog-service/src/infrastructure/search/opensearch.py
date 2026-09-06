import uuid

import httpx

from application.search_snapshot import ProductSearchSnapshot
from contracts.product import ProductView


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

    async def close(self) -> None:
        if self._owns_client:
            await self._client.aclose()

    async def search(self, query: str) -> list[ProductView]:
        response = await self._client.post(
            f"/{self._index_name}/_search",
            json={
                "query": {
                    "bool": {
                        "filter": [
                            {"term": {"is_active": True}},
                            {"term": {"owner_is_active": True}},
                        ],
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
                }
            },
        )
        if response.status_code == 404:
            return []
        response.raise_for_status()
        payload = response.json()
        hits = payload["hits"]["hits"]
        return [self._to_view(hit["_source"]) for hit in hits]

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
        response = await self._client.put(
            f"/{self._index_name}",
            json={
                "settings": {"number_of_shards": 1, "number_of_replicas": 0},
                "mappings": {
                    "properties": {
                        field: {
                            "type": "text",
                            "fields": {
                                "ru": {"type": "text", "analyzer": "russian"},
                                "en": {"type": "text", "analyzer": "english"},
                            },
                        }
                        for field in ("name", "description")
                    }
                },
            },
        )
        if response.status_code not in {200, 400}:
            response.raise_for_status()

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
