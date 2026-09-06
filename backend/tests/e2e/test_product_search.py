import asyncio
import time
import uuid
from collections.abc import Callable

import httpx
import pytest


async def _register_and_login(client: httpx.AsyncClient, *, email: str) -> str:
    password = "E2e-only-password-123"
    registration = await client.post(
        "/api/v1/auth/register", json={"email": email, "password": password}
    )
    assert registration.status_code == 201, registration.text
    login = await client.post(
        "/api/v1/auth/login", data={"username": email, "password": password}
    )
    assert login.status_code == 200, login.text
    return str(login.json()["access_token"])


async def _wait_for_search(
    client: httpx.AsyncClient,
    *,
    query: str,
    is_ready: Callable[[list[dict[str, object]]], bool],
    expectation: str,
) -> list[dict[str, object]]:
    deadline = time.monotonic() + 30
    while True:
        response = await client.get("/api/v1/products/search", params={"q": query})
        assert response.status_code == 200, response.text
        products = response.json()["data"]
        if is_ready(products):
            return products
        if time.monotonic() >= deadline:
            pytest.fail(f"search result did not satisfy {expectation}")
        await asyncio.sleep(0.2)


async def _wait_for_search_result(
    client: httpx.AsyncClient, *, query: str, product_id: str, expected: bool
) -> None:
    await _wait_for_search(
        client,
        query=query,
        is_ready=lambda products: (
            (product_id in {str(product["id"]) for product in products}) is expected
        ),
        expectation=f"product {product_id} to be present={expected}",
    )


async def _wait_for_search_results(
    client: httpx.AsyncClient, *, query: str, product_ids: set[str]
) -> list[dict[str, object]]:
    return await _wait_for_search(
        client,
        query=query,
        is_ready=lambda products: product_ids.issubset(
            {str(product["id"]) for product in products}
        ),
        expectation=f"products {product_ids} to become available",
    )


async def _create_product(
    client: httpx.AsyncClient, *, token: str, name: str, description: str
) -> str:
    response = await client.post(
        "/api/v1/products",
        headers={"Authorization": f"Bearer {token}"},
        json={
            "name": name,
            "description": description,
            "price": 19.99,
            "category": "E2E",
        },
    )
    assert response.status_code == 201, response.text
    return str(response.json()["data"]["id"])


@pytest.mark.asyncio
async def test_public_search_projects_product_snapshots_and_hides_deactivation(
    gateway_client: httpx.AsyncClient,
) -> None:
    suffix = uuid.uuid4().hex
    token = await _register_and_login(
        gateway_client, email=f"e2e-search-{suffix}@example.test"
    )
    query = f"needle{suffix}"
    created = await gateway_client.post(
        "/api/v1/products",
        headers={"Authorization": f"Bearer {token}"},
        json={
            "name": f"Product {query}",
            "description": "Catalog search end-to-end snapshot test",
            "price": 19.99,
            "category": "E2E",
        },
    )
    assert created.status_code == 201, created.text
    product_id = created.json()["data"]["id"]

    await _wait_for_search_result(
        gateway_client, query=query, product_id=product_id, expected=True
    )

    deactivated = await gateway_client.patch(
        f"/api/v1/products/{product_id}/deactivate",
        headers={"Authorization": f"Bearer {token}"},
    )
    assert deactivated.status_code == 200, deactivated.text
    await _wait_for_search_result(
        gateway_client, query=query, product_id=product_id, expected=False
    )


@pytest.mark.asyncio
async def test_public_search_applies_multilingual_relevance_and_safe_fuzziness(
    gateway_client: httpx.AsyncClient,
) -> None:
    suffix = uuid.uuid4().hex
    token = await _register_and_login(
        gateway_client, email=f"e2e-search-relevance-{suffix}@example.test"
    )
    name_match_id = await _create_product(
        gateway_client,
        token=token,
        name=f"Ranktoken{suffix}",
        description="Ordinary workshop tool",
    )
    description_match_id = await _create_product(
        gateway_client,
        token=token,
        name=f"Ordinary{suffix}",
        description=f"Useful ranktoken{suffix} workshop tool",
    )
    russian_id = await _create_product(
        gateway_client,
        token=token,
        name=f"Аккумуляторная дрель {suffix}",
        description="Инструмент для домашнего ремонта",
    )
    english_id = await _create_product(
        gateway_client,
        token=token,
        name=f"Workshop tool {suffix}",
        description="Cordless drilling tool for repairs",
    )

    ranked = await _wait_for_search_results(
        gateway_client,
        query=f"ranktoken{suffix}",
        product_ids={name_match_id, description_match_id},
    )
    ranked_ids = [str(product["id"]) for product in ranked]
    assert ranked_ids.index(name_match_id) < ranked_ids.index(description_match_id)

    await _wait_for_search_result(
        gateway_client, query="дрели", product_id=russian_id, expected=True
    )
    await _wait_for_search_result(
        gateway_client, query="drills", product_id=english_id, expected=True
    )
    await _wait_for_search_result(
        gateway_client, query="cordles", product_id=english_id, expected=True
    )
    await _wait_for_search_result(
        gateway_client, query="co", product_id=english_id, expected=False
    )
