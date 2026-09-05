import json
import uuid

import httpx
import pytest

from application.search_snapshot import ProductSearchSnapshot
from infrastructure.search.opensearch import OpenSearchProductSearch


@pytest.mark.asyncio
async def test_index_uses_product_revision_for_opensearch_external_versioning() -> None:
    request_log: list[httpx.Request] = []

    async def _handler(request: httpx.Request) -> httpx.Response:
        request_log.append(request)
        if request.url.path == "/catalog-products":
            return httpx.Response(200, json={"acknowledged": True})
        return httpx.Response(201, json={"result": "created"})

    client = httpx.AsyncClient(
        transport=httpx.MockTransport(_handler), base_url="http://opensearch"
    )
    search = OpenSearchProductSearch(
        base_url="http://opensearch", index_name="catalog-products", client=client
    )
    product_id = uuid.UUID("00000000-0000-0000-0000-000000000001")

    await search.index(
        ProductSearchSnapshot(
            product_id=product_id,
            user_id=uuid.UUID("00000000-0000-0000-0000-000000000002"),
            name="Cordless drill",
            description="18V brushless drill",
            category="Tools",
            price=99.0,
            is_active=True,
            search_revision=3,
        )
    )

    create_index, request = request_log
    assert create_index.url.path == "/catalog-products"
    assert json.loads(create_index.content) == {
        "settings": {"number_of_shards": 1, "number_of_replicas": 0}
    }
    assert request.method == "PUT"
    assert request.url.path == f"/catalog-products/_doc/{product_id}"
    assert dict(request.url.params) == {"version": "3", "version_type": "external_gte"}
    assert json.loads(request.content) == {
        "id": str(product_id),
        "user_id": "00000000-0000-0000-0000-000000000002",
        "name": "Cordless drill",
        "description": "18V brushless drill",
        "category": "Tools",
        "price": 99.0,
        "is_active": True,
    }
    await client.aclose()


@pytest.mark.asyncio
async def test_search_returns_no_matches_before_the_index_exists() -> None:
    client = httpx.AsyncClient(
        transport=httpx.MockTransport(lambda _request: httpx.Response(404)),
        base_url="http://opensearch",
    )
    search = OpenSearchProductSearch(
        base_url="http://opensearch", index_name="catalog-products", client=client
    )

    assert await search.search("drill") == []
    await client.aclose()
