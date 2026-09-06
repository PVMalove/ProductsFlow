import uuid

import pytest

from application.queries.search_products import SearchProductsQueryHandler
from contracts.product import ProductView


class FakeProductSearch:
    def __init__(self) -> None:
        self.queries: list[str] = []

    async def search(self, query: str) -> list[ProductView]:
        self.queries.append(query)
        return [
            ProductView(
                id=uuid.UUID("00000000-0000-0000-0000-000000000001"),
                name="Cordless drill",
                description="18V brushless drill",
                price=99.0,
                category="Tools",
                user_id=uuid.UUID("00000000-0000-0000-0000-000000000002"),
                is_active=True,
            )
        ]


async def test_public_search_returns_bff_envelope_with_active_text_matches(
    catalog_client,
) -> None:
    from api.dependencies import get_search_products_handler
    from api.main import app

    search = FakeProductSearch()
    app.dependency_overrides[get_search_products_handler] = lambda: (
        SearchProductsQueryHandler(search)
    )
    try:
        response = await catalog_client.get(
            "/api/v1/products/search", params={"q": "drill"}
        )
    finally:
        app.dependency_overrides.pop(get_search_products_handler, None)

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
        "meta": {},
    }
    assert search.queries == ["drill"]


@pytest.mark.parametrize("params", [{}, {"q": "x"}, {"q": "x" * 101}])
async def test_public_search_rejects_missing_or_out_of_bounds_query_with_bff_error(
    catalog_client, params: dict[str, str]
) -> None:
    from api.dependencies import get_search_products_handler
    from api.main import app

    app.dependency_overrides[get_search_products_handler] = lambda: (
        SearchProductsQueryHandler(FakeProductSearch())
    )
    try:
        response = await catalog_client.get("/api/v1/products/search", params=params)
    finally:
        app.dependency_overrides.pop(get_search_products_handler, None)

    assert response.status_code == 422
    body = response.json()
    assert body["error"]["code"] == "VALIDATION_ERROR"
    assert body["error"]["message"] == "Некорректные данные запроса"
    assert [detail["field"] for detail in body["error"]["details"]] == ["q"]
