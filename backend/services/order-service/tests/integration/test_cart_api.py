"""Сквозной HTTP через реальный Postgres + FakeIdentityClient (issue #369,
Seams for TDD #6 — обязательный тест DoD п.6, по образцу
payment's/inventory's test_*_api.py): 401 без токена, счастливый путь CRUD
для владельца, 403 для другого аутентифицированного пользователя на
line-level эндпоинтах (D5)."""

import uuid

import httpx
import pytest

from tests.integration.fake_identity_client import FakeIdentityClient

pytestmark = pytest.mark.asyncio(loop_scope="session")


async def test_get_cart_requires_authentication(cart_client: httpx.AsyncClient) -> None:
    response = await cart_client.get("/api/v1/cart")

    assert response.status_code == 401


async def test_add_line_requires_authentication(cart_client: httpx.AsyncClient) -> None:
    response = await cart_client.post(
        "/api/v1/cart/lines", json={"product_id": str(uuid.uuid4()), "quantity": 1}
    )

    assert response.status_code == 401


async def test_get_cart_for_new_user_is_empty(
    cart_client: httpx.AsyncClient, identity_client: FakeIdentityClient
) -> None:
    identity_client.register("user-token", user_id=uuid.uuid4())

    response = await cart_client.get(
        "/api/v1/cart", headers={"Authorization": "Bearer user-token"}
    )

    assert response.status_code == 200
    assert response.json()["data"]["lines"] == []


async def test_add_line_creates_it_without_a_prior_get(
    cart_client: httpx.AsyncClient, identity_client: FakeIdentityClient
) -> None:
    identity_client.register("user-token", user_id=uuid.uuid4())
    product_id = str(uuid.uuid4())

    response = await cart_client.post(
        "/api/v1/cart/lines",
        json={"product_id": product_id, "quantity": 2},
        headers={"Authorization": "Bearer user-token"},
    )

    assert response.status_code == 201
    body = response.json()["data"]
    assert body["product_id"] == product_id
    assert body["quantity"] == 2


async def test_add_line_invalid_quantity_returns_400(
    cart_client: httpx.AsyncClient, identity_client: FakeIdentityClient
) -> None:
    identity_client.register("user-token", user_id=uuid.uuid4())

    response = await cart_client.post(
        "/api/v1/cart/lines",
        json={"product_id": str(uuid.uuid4()), "quantity": 0},
        headers={"Authorization": "Bearer user-token"},
    )

    assert response.status_code == 400
    assert response.json()["error"]["code"] == "invalid_quantity"


async def test_add_line_twice_merges_quantity(
    cart_client: httpx.AsyncClient, identity_client: FakeIdentityClient
) -> None:
    identity_client.register("user-token", user_id=uuid.uuid4())
    headers = {"Authorization": "Bearer user-token"}
    product_id = str(uuid.uuid4())

    first = await cart_client.post(
        "/api/v1/cart/lines",
        json={"product_id": product_id, "quantity": 2},
        headers=headers,
    )
    second = await cart_client.post(
        "/api/v1/cart/lines",
        json={"product_id": product_id, "quantity": 3},
        headers=headers,
    )

    assert first.status_code == 201
    assert second.status_code == 201
    assert second.json()["data"]["id"] == first.json()["data"]["id"]
    assert second.json()["data"]["quantity"] == 5

    cart = await cart_client.get("/api/v1/cart", headers=headers)
    assert len(cart.json()["data"]["lines"]) == 1


async def test_owner_can_update_and_delete_their_line(
    cart_client: httpx.AsyncClient, identity_client: FakeIdentityClient
) -> None:
    identity_client.register("user-token", user_id=uuid.uuid4())
    headers = {"Authorization": "Bearer user-token"}
    add_response = await cart_client.post(
        "/api/v1/cart/lines",
        json={"product_id": str(uuid.uuid4()), "quantity": 1},
        headers=headers,
    )
    line_id = add_response.json()["data"]["id"]

    update_response = await cart_client.patch(
        f"/api/v1/cart/lines/{line_id}", json={"quantity": 9}, headers=headers
    )
    assert update_response.status_code == 200
    assert update_response.json()["data"]["quantity"] == 9

    delete_response = await cart_client.delete(
        f"/api/v1/cart/lines/{line_id}", headers=headers
    )
    assert delete_response.status_code == 200

    cart = await cart_client.get("/api/v1/cart", headers=headers)
    assert cart.json()["data"]["lines"] == []


async def test_another_authenticated_user_is_denied_on_update_and_delete(
    cart_client: httpx.AsyncClient, identity_client: FakeIdentityClient
) -> None:
    identity_client.register("owner-token", user_id=uuid.uuid4())
    identity_client.register("intruder-token", user_id=uuid.uuid4())
    owner_headers = {"Authorization": "Bearer owner-token"}
    intruder_headers = {"Authorization": "Bearer intruder-token"}
    add_response = await cart_client.post(
        "/api/v1/cart/lines",
        json={"product_id": str(uuid.uuid4()), "quantity": 1},
        headers=owner_headers,
    )
    line_id = add_response.json()["data"]["id"]

    update_response = await cart_client.patch(
        f"/api/v1/cart/lines/{line_id}", json={"quantity": 5}, headers=intruder_headers
    )
    delete_response = await cart_client.delete(
        f"/api/v1/cart/lines/{line_id}", headers=intruder_headers
    )

    assert update_response.status_code == 403
    assert update_response.json()["error"]["code"] == "CART_ACCESS_DENIED"
    assert delete_response.status_code == 403
    assert delete_response.json()["error"]["code"] == "CART_ACCESS_DENIED"

    # Не тронуто чужим запросом.
    owner_cart = await cart_client.get("/api/v1/cart", headers=owner_headers)
    assert owner_cart.json()["data"]["lines"][0]["quantity"] == 1


async def test_unauthenticated_request_is_denied_on_update_and_delete(
    cart_client: httpx.AsyncClient, identity_client: FakeIdentityClient
) -> None:
    identity_client.register("owner-token", user_id=uuid.uuid4())
    add_response = await cart_client.post(
        "/api/v1/cart/lines",
        json={"product_id": str(uuid.uuid4()), "quantity": 1},
        headers={"Authorization": "Bearer owner-token"},
    )
    line_id = add_response.json()["data"]["id"]

    update_response = await cart_client.patch(
        f"/api/v1/cart/lines/{line_id}", json={"quantity": 5}
    )
    delete_response = await cart_client.delete(f"/api/v1/cart/lines/{line_id}")

    assert update_response.status_code == 401
    assert delete_response.status_code == 401


async def test_update_unknown_line_returns_404(
    cart_client: httpx.AsyncClient, identity_client: FakeIdentityClient
) -> None:
    identity_client.register("user-token", user_id=uuid.uuid4())

    response = await cart_client.patch(
        f"/api/v1/cart/lines/{uuid.uuid4()}",
        json={"quantity": 1},
        headers={"Authorization": "Bearer user-token"},
    )

    assert response.status_code == 404
    assert response.json()["error"]["code"] == "CART_LINE_NOT_FOUND"


async def test_delete_unknown_line_returns_404(
    cart_client: httpx.AsyncClient, identity_client: FakeIdentityClient
) -> None:
    identity_client.register("user-token", user_id=uuid.uuid4())

    response = await cart_client.delete(
        f"/api/v1/cart/lines/{uuid.uuid4()}",
        headers={"Authorization": "Bearer user-token"},
    )

    assert response.status_code == 404
    assert response.json()["error"]["code"] == "CART_LINE_NOT_FOUND"
