import uuid
from collections.abc import Iterator
from contextlib import contextmanager

import pytest
from kernel_platform.pagination import Page, PageInfo

from application.queries.search_products import SearchProductsQueryHandler
from application.search_cursor import (
    ProductSortOption,
    SearchCursor,
    decode_search_cursor,
    encode_search_cursor,
)
from contracts.product import ProductView

_PRODUCT = ProductView(
    id=uuid.UUID("00000000-0000-0000-0000-000000000001"),
    name="Cordless drill",
    description="18V brushless drill",
    price=99.0,
    category="Tools",
    user_id=uuid.UUID("00000000-0000-0000-0000-000000000002"),
    is_active=True,
)


class FakeProductSearch:
    """Records every argument the endpoint forwards to the search port, and
    returns a scripted `Page` so tests can assert the BFF envelope shape."""

    def __init__(self, page: Page[ProductView] | None = None) -> None:
        self.calls: list[dict[str, object]] = []
        self._page = page or Page(
            items=[_PRODUCT],
            page_info=PageInfo(
                next_cursor=None, prev_cursor=None, has_more=False, has_prev=False
            ),
        )

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


@contextmanager
def _overridden_search(search: FakeProductSearch) -> Iterator[None]:
    from api.dependencies import get_search_products_handler
    from api.main import app

    app.dependency_overrides[get_search_products_handler] = lambda: (
        SearchProductsQueryHandler(search)
    )
    try:
        yield
    finally:
        app.dependency_overrides.pop(get_search_products_handler, None)


async def test_public_search_returns_bff_envelope_with_active_text_matches(
    catalog_client,
) -> None:
    search = FakeProductSearch()
    with _overridden_search(search):
        response = await catalog_client.get(
            "/api/v1/products/search", params={"q": "drill"}
        )

    assert response.status_code == 200
    assert response.json() == {
        "data": [
            {
                "id": "00000000-0000-0000-0000-000000000001",
                "name": "Cordless drill",
                "description": "18V brushless drill",
                "price": 99.0,
                "category": "Tools",
                "user_id": "00000000-0000-0000-0000-000000000002",
                "is_active": True,
            }
        ],
        "meta": {
            "next_cursor": None,
            "prev_cursor": None,
            "has_more": False,
            "has_prev": False,
        },
    }
    assert search.calls == [
        {
            "query": "drill",
            "category": None,
            "min_price": None,
            "max_price": None,
            "sort": ProductSortOption.RELEVANCE,
            "limit": 20,
            "cursor": None,
        }
    ]


@pytest.mark.parametrize("params", [{}, {"q": "x"}, {"q": "x" * 101}])
async def test_public_search_rejects_missing_or_out_of_bounds_query_with_bff_error(
    catalog_client, params: dict[str, str]
) -> None:
    with _overridden_search(FakeProductSearch()):
        response = await catalog_client.get("/api/v1/products/search", params=params)

    assert response.status_code == 422
    body = response.json()
    assert body["error"]["code"] == "VALIDATION_ERROR"
    assert body["error"]["message"] == "Некорректные данные запроса"
    assert [detail["field"] for detail in body["error"]["details"]] == ["q"]


async def test_public_search_passes_category_and_inclusive_price_range_filters(
    catalog_client,
) -> None:
    search = FakeProductSearch()
    with _overridden_search(search):
        response = await catalog_client.get(
            "/api/v1/products/search",
            params={
                "q": "drill",
                "category": "Tools",
                "min_price": 10,
                "max_price": 99,
            },
        )

    assert response.status_code == 200
    assert search.calls[0]["category"] == "Tools"
    assert search.calls[0]["min_price"] == 10.0
    assert search.calls[0]["max_price"] == 99.0


@pytest.mark.parametrize("sort", ["relevance", "price_asc", "price_desc", "newest"])
async def test_public_search_passes_each_supported_sort_option(
    catalog_client, sort: str
) -> None:
    search = FakeProductSearch()
    with _overridden_search(search):
        response = await catalog_client.get(
            "/api/v1/products/search", params={"q": "drill", "sort": sort}
        )

    assert response.status_code == 200
    assert search.calls[0]["sort"] == ProductSortOption(sort)


async def test_public_search_combines_category_price_sort_and_cursor_in_one_request(
    catalog_client,
) -> None:
    product_id = uuid.UUID("00000000-0000-0000-0000-000000000077")
    cursor = SearchCursor(
        sort=ProductSortOption.PRICE_DESC, sort_value=42.0, product_id=product_id
    )
    token = encode_search_cursor(cursor)
    search = FakeProductSearch()
    with _overridden_search(search):
        response = await catalog_client.get(
            "/api/v1/products/search",
            params={
                "q": "drill",
                "category": "Tools",
                "min_price": 10,
                "max_price": 99,
                "sort": "price_desc",
                "after": token,
            },
        )

    assert response.status_code == 200
    assert search.calls[0] == {
        "query": "drill",
        "category": "Tools",
        "min_price": 10.0,
        "max_price": 99.0,
        "sort": ProductSortOption.PRICE_DESC,
        "limit": 20,
        "cursor": cursor,
    }


async def test_public_search_rejects_an_unsupported_sort_value(catalog_client) -> None:
    with _overridden_search(FakeProductSearch()):
        response = await catalog_client.get(
            "/api/v1/products/search", params={"q": "drill", "sort": "cheapest"}
        )

    assert response.status_code == 422
    assert response.json()["error"]["code"] == "VALIDATION_ERROR"


async def test_public_search_decodes_a_valid_cursor_matching_the_requested_sort(
    catalog_client,
) -> None:
    product_id = uuid.UUID("00000000-0000-0000-0000-000000000042")
    cursor = SearchCursor(
        sort=ProductSortOption.PRICE_ASC, sort_value=42.0, product_id=product_id
    )
    token = encode_search_cursor(cursor)
    search = FakeProductSearch()
    with _overridden_search(search):
        response = await catalog_client.get(
            "/api/v1/products/search",
            params={"q": "drill", "sort": "price_asc", "after": token},
        )

    assert response.status_code == 200
    assert search.calls[0]["cursor"] == cursor


async def test_public_search_rejects_a_cursor_encoded_for_a_different_sort(
    catalog_client,
) -> None:
    token = encode_search_cursor(
        SearchCursor(
            sort=ProductSortOption.PRICE_ASC,
            sort_value=42.0,
            product_id=uuid.uuid4(),
        )
    )
    with _overridden_search(FakeProductSearch()):
        response = await catalog_client.get(
            "/api/v1/products/search",
            params={"q": "drill", "sort": "newest", "after": token},
        )

    assert response.status_code == 400
    assert response.json()["error"]["code"] == "PRODUCT_SEARCH_INVALID_CURSOR"


async def test_public_search_rejects_a_malformed_cursor(catalog_client) -> None:
    with _overridden_search(FakeProductSearch()):
        response = await catalog_client.get(
            "/api/v1/products/search",
            params={"q": "drill", "after": "not-a-valid-cursor"},
        )

    assert response.status_code == 400
    assert response.json()["error"]["code"] == "PRODUCT_SEARCH_INVALID_CURSOR"


async def test_public_search_page_transition_exposes_next_cursor_in_meta(
    catalog_client,
) -> None:
    boundary_product_id = uuid.uuid4()
    next_token = encode_search_cursor(
        SearchCursor(
            sort=ProductSortOption.RELEVANCE,
            sort_value=1.5,
            product_id=boundary_product_id,
        )
    )
    first_page = Page(
        items=[_PRODUCT],
        page_info=PageInfo(
            next_cursor=next_token, prev_cursor=None, has_more=True, has_prev=False
        ),
    )
    search = FakeProductSearch(first_page)
    with _overridden_search(search):
        first_response = await catalog_client.get(
            "/api/v1/products/search", params={"q": "drill"}
        )

        assert first_response.status_code == 200
        assert first_response.json()["meta"] == {
            "next_cursor": next_token,
            "prev_cursor": None,
            "has_more": True,
            "has_prev": False,
        }

        second_response = await catalog_client.get(
            "/api/v1/products/search", params={"q": "drill", "after": next_token}
        )

    assert second_response.status_code == 200
    forwarded_cursor = search.calls[-1]["cursor"]
    assert forwarded_cursor == decode_search_cursor(
        next_token, expected_sort=ProductSortOption.RELEVANCE
    )
