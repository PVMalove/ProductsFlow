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
                        "filter": [{"term": {"is_active": True}}],
                        "must": [
                            {
                                "multi_match": {
                                    "query": query,
                                    "fields": ["name", "description"],
                                }
                            }
                        ],
                    }
                }
            },
        )
        response.raise_for_status()
        payload = response.json()
        hits = payload["hits"]["hits"]
        return [self._to_view(hit["_source"]) for hit in hits]

    async def index(self, snapshot: ProductSearchSnapshot) -> None:
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
            },
        )
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
