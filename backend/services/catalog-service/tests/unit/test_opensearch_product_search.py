import json
import uuid
from datetime import datetime

import httpx
import pytest

from application.search_cursor import (
    ProductSortOption,
    SearchCursor,
    decode_search_cursor,
)
from application.search_snapshot import ProductSearchSnapshot
from infrastructure.search.opensearch import OpenSearchProductSearch

_CREATED_AT = datetime(2026, 1, 1, 12, 0, 0)


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
            created_at=_CREATED_AT,
        ),
        owner_is_active=True,
    )

    create_index, request = request_log
    assert create_index.url.path == "/catalog-products"
    assert json.loads(create_index.content)["settings"] == {
        "number_of_shards": 1,
        "number_of_replicas": 0,
        "analysis": {
            "normalizer": {"lowercase": {"type": "custom", "filter": ["lowercase"]}}
        },
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
        "owner_is_active": True,
        "created_at": _CREATED_AT.isoformat(),
    }
    await client.aclose()


@pytest.mark.asyncio
async def test_search_configures_multilingual_fields_and_weighted_fuzzy_matching() -> (
    None
):
    request_log: list[httpx.Request] = []

    async def _handler(request: httpx.Request) -> httpx.Response:
        request_log.append(request)
        if request.url.path == "/catalog-products":
            return httpx.Response(200, json={"acknowledged": True})
        if request.url.path.endswith("/_search"):
            return httpx.Response(200, json={"hits": {"hits": []}})
        return httpx.Response(201, json={"result": "created"})

    client = httpx.AsyncClient(
        transport=httpx.MockTransport(_handler), base_url="http://opensearch"
    )
    search = OpenSearchProductSearch(
        base_url="http://opensearch", index_name="catalog-products", client=client
    )

    await search.index(
        ProductSearchSnapshot(
            product_id=uuid.UUID("00000000-0000-0000-0000-000000000001"),
            user_id=uuid.UUID("00000000-0000-0000-0000-000000000002"),
            name="Аккумуляторная дрель",
            description="Cordless drill for home repairs",
            category="Tools",
            price=99.0,
            is_active=True,
            search_revision=1,
            created_at=_CREATED_AT,
        ),
        owner_is_active=True,
    )
    await search.search("дрел")

    create_index, _, search_request = request_log
    assert json.loads(create_index.content)["mappings"] == {
        "properties": {
            **{
                field: {
                    "type": "text",
                    "fields": {
                        "ru": {"type": "text", "analyzer": "russian"},
                        "en": {"type": "text", "analyzer": "english"},
                    },
                }
                for field in ("name", "description")
            },
            "id": {"type": "keyword"},
            "category": {"type": "keyword", "normalizer": "lowercase"},
            "price": {"type": "double"},
            "created_at": {"type": "date"},
        }
    }
    assert json.loads(search_request.content)["query"]["bool"]["must"] == [
        {
            "multi_match": {
                "query": "дрел",
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
    await client.aclose()


@pytest.mark.asyncio
async def test_index_migrates_existing_index_and_reindexes_its_documents() -> None:
    request_log: list[httpx.Request] = []

    async def _handler(request: httpx.Request) -> httpx.Response:
        request_log.append(request)
        if request.url.path == "/catalog-products":
            return httpx.Response(
                400,
                json={"error": {"type": "resource_already_exists_exception"}},
            )
        if request.url.path == "/catalog-products/_mapping" and request.method == "GET":
            return httpx.Response(
                200,
                json={
                    "catalog-products": {
                        "mappings": {"properties": {"name": {"type": "text"}}}
                    }
                },
            )
        if request.url.path == "/catalog-products/_mapping":
            return httpx.Response(200, json={"acknowledged": True})
        if request.url.path == "/catalog-products/_update_by_query":
            return httpx.Response(200, json={"updated": 1})
        return httpx.Response(201, json={"result": "created"})

    client = httpx.AsyncClient(
        transport=httpx.MockTransport(_handler), base_url="http://opensearch"
    )
    search = OpenSearchProductSearch(
        base_url="http://opensearch", index_name="catalog-products", client=client
    )

    await search.index(
        ProductSearchSnapshot(
            product_id=uuid.UUID("00000000-0000-0000-0000-000000000001"),
            user_id=uuid.UUID("00000000-0000-0000-0000-000000000002"),
            name="Cordless drill",
            description="18V brushless drill",
            category="Tools",
            price=99.0,
            is_active=True,
            search_revision=1,
            created_at=_CREATED_AT,
        ),
        owner_is_active=True,
    )

    assert [(request.method, request.url.path) for request in request_log] == [
        ("PUT", "/catalog-products"),
        ("GET", "/catalog-products/_mapping"),
        ("PUT", "/catalog-products/_mapping"),
        ("POST", "/catalog-products/_update_by_query"),
        ("PUT", "/catalog-products/_doc/00000000-0000-0000-0000-000000000001"),
    ]
    assert json.loads(request_log[3].content) == {"query": {"match_all": {}}}
    await client.aclose()


@pytest.mark.asyncio
async def test_index_checks_an_existing_mapping_only_once_per_worker() -> None:
    request_log: list[httpx.Request] = []

    async def _handler(request: httpx.Request) -> httpx.Response:
        request_log.append(request)
        if request.url.path == "/catalog-products":
            return httpx.Response(
                400,
                json={"error": {"type": "resource_already_exists_exception"}},
            )
        if request.url.path == "/catalog-products/_mapping":
            return httpx.Response(
                200,
                json={
                    "catalog-products": {
                        "mappings": {
                            "properties": (OpenSearchProductSearch._index_properties())
                        }
                    }
                },
            )
        return httpx.Response(201, json={"result": "created"})

    client = httpx.AsyncClient(
        transport=httpx.MockTransport(_handler), base_url="http://opensearch"
    )
    search = OpenSearchProductSearch(
        base_url="http://opensearch", index_name="catalog-products", client=client
    )
    owner_id = uuid.UUID("00000000-0000-0000-0000-000000000002")

    for product_id in (
        uuid.UUID("00000000-0000-0000-0000-000000000001"),
        uuid.UUID("00000000-0000-0000-0000-000000000003"),
    ):
        await search.index(
            ProductSearchSnapshot(
                product_id=product_id,
                user_id=owner_id,
                name="Cordless drill",
                description="18V brushless drill",
                category="Tools",
                price=99.0,
                is_active=True,
                search_revision=1,
                created_at=_CREATED_AT,
            ),
            owner_is_active=True,
        )

    assert [(request.method, request.url.path) for request in request_log] == [
        ("PUT", "/catalog-products"),
        ("GET", "/catalog-products/_mapping"),
        ("PUT", "/catalog-products/_doc/00000000-0000-0000-0000-000000000001"),
        ("PUT", "/catalog-products/_doc/00000000-0000-0000-0000-000000000003"),
    ]
    await client.aclose()


@pytest.mark.asyncio
async def test_search_filters_by_active_product_and_active_owner() -> None:
    request_log: list[httpx.Request] = []

    async def _handler(request: httpx.Request) -> httpx.Response:
        request_log.append(request)
        return httpx.Response(200, json={"hits": {"hits": []}})

    client = httpx.AsyncClient(
        transport=httpx.MockTransport(_handler), base_url="http://opensearch"
    )
    search = OpenSearchProductSearch(
        base_url="http://opensearch", index_name="catalog-products", client=client
    )

    await search.search("drill")

    [request] = request_log
    body = json.loads(request.content)
    assert body["query"]["bool"]["filter"] == [
        {"term": {"is_active": True}},
        {"term": {"owner_is_active": True}},
    ]
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

    page = await search.search("drill")
    assert page.items == []
    assert page.page_info.has_more is False
    assert page.page_info.next_cursor is None
    await client.aclose()


@pytest.mark.asyncio
async def test_set_owner_active_updates_every_indexed_product_of_the_owner() -> None:
    user_id = uuid.UUID("00000000-0000-0000-0000-000000000002")
    request_log: list[httpx.Request] = []

    async def _handler(request: httpx.Request) -> httpx.Response:
        request_log.append(request)
        return httpx.Response(200, json={"updated": 3})

    client = httpx.AsyncClient(
        transport=httpx.MockTransport(_handler), base_url="http://opensearch"
    )
    search = OpenSearchProductSearch(
        base_url="http://opensearch", index_name="catalog-products", client=client
    )

    await search.set_owner_active(user_id, is_active=False)

    [request] = request_log
    assert request.method == "POST"
    assert request.url.path == "/catalog-products/_update_by_query"
    body = json.loads(request.content)
    assert body["query"] == {"term": {"user_id": str(user_id)}}
    assert body["script"]["params"] == {"is_active": False}
    await client.aclose()


@pytest.mark.asyncio
async def test_set_owner_active_is_a_noop_before_the_index_exists() -> None:
    client = httpx.AsyncClient(
        transport=httpx.MockTransport(lambda _request: httpx.Response(404)),
        base_url="http://opensearch",
    )
    search = OpenSearchProductSearch(
        base_url="http://opensearch", index_name="catalog-products", client=client
    )

    await search.set_owner_active(uuid.uuid4(), is_active=True)
    await client.aclose()


@pytest.mark.asyncio
async def test_search_filters_by_category_and_inclusive_price_range() -> None:
    request_log: list[httpx.Request] = []

    async def _handler(request: httpx.Request) -> httpx.Response:
        request_log.append(request)
        return httpx.Response(200, json={"hits": {"hits": []}})

    client = httpx.AsyncClient(
        transport=httpx.MockTransport(_handler), base_url="http://opensearch"
    )
    search = OpenSearchProductSearch(
        base_url="http://opensearch", index_name="catalog-products", client=client
    )

    await search.search("drill", category="Tools", min_price=10.0, max_price=99.0)

    [request] = request_log
    body = json.loads(request.content)
    assert body["query"]["bool"]["filter"] == [
        {"term": {"is_active": True}},
        {"term": {"owner_is_active": True}},
        {"term": {"category": "Tools"}},
        {"range": {"price": {"gte": 10.0, "lte": 99.0}}},
    ]
    await client.aclose()


@pytest.mark.parametrize(
    ("sort", "expected_clause"),
    [
        (ProductSortOption.RELEVANCE, [{"_score": "desc"}, {"id": "asc"}]),
        (ProductSortOption.PRICE_ASC, [{"price": "asc"}, {"id": "asc"}]),
        (ProductSortOption.PRICE_DESC, [{"price": "desc"}, {"id": "asc"}]),
        (ProductSortOption.NEWEST, [{"created_at": "desc"}, {"id": "asc"}]),
    ],
)
@pytest.mark.asyncio
async def test_search_sort_clause_ends_with_product_id_tie_breaker(
    sort: ProductSortOption, expected_clause: list[dict[str, str]]
) -> None:
    request_log: list[httpx.Request] = []

    async def _handler(request: httpx.Request) -> httpx.Response:
        request_log.append(request)
        return httpx.Response(200, json={"hits": {"hits": []}})

    client = httpx.AsyncClient(
        transport=httpx.MockTransport(_handler), base_url="http://opensearch"
    )
    search = OpenSearchProductSearch(
        base_url="http://opensearch", index_name="catalog-products", client=client
    )

    await search.search("drill", sort=sort)

    [request] = request_log
    assert json.loads(request.content)["sort"] == expected_clause
    await client.aclose()


@pytest.mark.asyncio
async def test_search_forwards_cursor_as_opensearch_search_after() -> None:
    request_log: list[httpx.Request] = []

    async def _handler(request: httpx.Request) -> httpx.Response:
        request_log.append(request)
        return httpx.Response(200, json={"hits": {"hits": []}})

    client = httpx.AsyncClient(
        transport=httpx.MockTransport(_handler), base_url="http://opensearch"
    )
    search = OpenSearchProductSearch(
        base_url="http://opensearch", index_name="catalog-products", client=client
    )
    product_id = uuid.UUID("00000000-0000-0000-0000-000000000009")

    await search.search(
        "drill",
        sort=ProductSortOption.PRICE_ASC,
        cursor=SearchCursor(
            sort=ProductSortOption.PRICE_ASC, sort_value=42.5, product_id=product_id
        ),
    )

    [request] = request_log
    assert json.loads(request.content)["search_after"] == [42.5, str(product_id)]
    await client.aclose()


@pytest.mark.asyncio
async def test_search_builds_next_cursor_from_the_last_hit_when_more_remain() -> None:
    product_ids = [f"00000000-0000-0000-0000-{index:012d}" for index in range(1, 4)]

    async def _handler(_request: httpx.Request) -> httpx.Response:
        return httpx.Response(
            200,
            json={
                "hits": {
                    "hits": [
                        {
                            "sort": [10.0 + index, product_id],
                            "_source": {
                                "id": product_id,
                                "user_id": "00000000-0000-0000-0000-000000000099",
                                "name": "Cordless drill",
                                "description": "18V brushless drill",
                                "category": "Tools",
                                "price": 10.0 + index,
                                "is_active": True,
                            },
                        }
                        for index, product_id in enumerate(product_ids)
                    ]
                }
            },
        )

    client = httpx.AsyncClient(
        transport=httpx.MockTransport(_handler), base_url="http://opensearch"
    )
    search = OpenSearchProductSearch(
        base_url="http://opensearch", index_name="catalog-products", client=client
    )

    page = await search.search("drill", sort=ProductSortOption.PRICE_ASC, limit=2)

    assert [item.id for item in page.items] == [
        uuid.UUID(product_ids[0]),
        uuid.UUID(product_ids[1]),
    ]
    assert page.page_info.has_more is True
    assert page.page_info.next_cursor is not None
    cursor = decode_search_cursor(
        page.page_info.next_cursor, expected_sort=ProductSortOption.PRICE_ASC
    )
    assert cursor.sort_value == 11.0
    assert cursor.product_id == uuid.UUID(product_ids[1])
    await client.aclose()
