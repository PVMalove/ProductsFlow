import uuid

import httpx
import pytest


async def _register_and_login(client: httpx.AsyncClient, *, email: str) -> str:
    password = "E2e-only-password-123"
    registration = await client.post(
        "/api/v1/auth/register",
        json={"email": email, "password": password},
    )
    assert registration.status_code == 201, registration.text

    login = await client.post(
        "/api/v1/auth/login",
        data={"username": email, "password": password},
    )
    assert login.status_code == 200, login.text
    return str(login.json()["access_token"])


@pytest.mark.asyncio
async def test_owner_keeps_direct_access_to_deactivated_product(
    gateway_client: httpx.AsyncClient,
) -> None:
    suffix = uuid.uuid4().hex
    owner_token = await _register_and_login(
        gateway_client, email=f"e2e-owner-{suffix}@example.test"
    )
    viewer_token = await _register_and_login(
        gateway_client, email=f"e2e-viewer-{suffix}@example.test"
    )
    owner_headers = {"Authorization": f"Bearer {owner_token}"}
    viewer_headers = {"Authorization": f"Bearer {viewer_token}"}

    created = await gateway_client.post(
        "/api/v1/products",
        headers=owner_headers,
        json={
            "name": f"E2E product {suffix}",
            "description": "Created through the E2E Gateway.",
            "price": 19.99,
            "category": "E2E",
        },
    )
    assert created.status_code == 201, created.text
    product_id = created.json()["data"]["id"]

    visible_to_viewer = await gateway_client.get(
        f"/api/v1/products/{product_id}", headers=viewer_headers
    )
    assert visible_to_viewer.status_code == 200, visible_to_viewer.text

    deactivated = await gateway_client.patch(
        f"/api/v1/products/{product_id}/deactivate", headers=owner_headers
    )
    assert deactivated.status_code == 200, deactivated.text

    visible_to_owner = await gateway_client.get(
        f"/api/v1/products/{product_id}", headers=owner_headers
    )
    assert visible_to_owner.status_code == 200, visible_to_owner.text

    hidden_from_viewer = await gateway_client.get(
        f"/api/v1/products/{product_id}", headers=viewer_headers
    )
    assert hidden_from_viewer.status_code == 404, hidden_from_viewer.text


@pytest.mark.asyncio
async def test_gateway_denies_a_path_outside_its_allow_list(
    gateway_client: httpx.AsyncClient,
) -> None:
    response = await gateway_client.get("/internal/health")

    assert response.status_code == 404, response.text
