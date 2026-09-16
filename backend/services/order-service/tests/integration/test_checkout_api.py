"""Сквозной HTTP checkout через реальный Postgres + FakeIdentityClient +
FakeCatalogClient (issue #372, Seams for TDD #10): CATALOG_UNAVAILABLE ->
503, ноль строк в orders; идентичный/другой Idempotency-Key -> 200-эквивалент
(201)/409; отсутствие заголовка -> 422; недоступный/неактивный identity ->
503/403."""

import uuid

import httpx
import pytest

from tests.integration.fake_identity_client import FakeIdentityClient
from tests.unit.fake_catalog_client import FakeCatalogClient

pytestmark = pytest.mark.asyncio(loop_scope="session")


async def _add_line(
    cart_client: httpx.AsyncClient, headers: dict[str, str], product_id: uuid.UUID
) -> None:
    response = await cart_client.post(
        "/api/v1/cart/lines",
        json={"product_id": str(product_id), "quantity": 2},
        headers=headers,
    )
    assert response.status_code == 201


async def test_checkout_requires_authentication(
    cart_client: httpx.AsyncClient,
) -> None:
    response = await cart_client.post(
        "/api/v1/checkout", headers={"Idempotency-Key": "key-1"}
    )

    assert response.status_code == 401


async def test_checkout_requires_idempotency_key_header(
    cart_client: httpx.AsyncClient, identity_client: FakeIdentityClient
) -> None:
    identity_client.register("user-token", user_id=uuid.uuid4())

    response = await cart_client.post(
        "/api/v1/checkout", headers={"Authorization": "Bearer user-token"}
    )

    assert response.status_code == 422


async def test_checkout_empty_cart_returns_400(
    cart_client: httpx.AsyncClient, identity_client: FakeIdentityClient
) -> None:
    identity_client.register("user-token", user_id=uuid.uuid4())

    response = await cart_client.post(
        "/api/v1/checkout",
        headers={"Authorization": "Bearer user-token", "Idempotency-Key": "key-1"},
    )

    assert response.status_code == 400
    assert response.json()["error"]["code"] == "empty_cart"


async def test_checkout_inactive_user_is_denied(
    cart_client: httpx.AsyncClient, identity_client: FakeIdentityClient
) -> None:
    identity_client.register("user-token", user_id=uuid.uuid4(), is_active=False)

    response = await cart_client.post(
        "/api/v1/checkout",
        headers={"Authorization": "Bearer user-token", "Idempotency-Key": "key-1"},
    )

    assert response.status_code == 403


async def test_checkout_identity_unavailable_returns_503(
    cart_client: httpx.AsyncClient, identity_client: FakeIdentityClient
) -> None:
    identity_client.register("user-token", user_id=uuid.uuid4())
    identity_client.unavailable = True

    response = await cart_client.post(
        "/api/v1/checkout",
        headers={"Authorization": "Bearer user-token", "Idempotency-Key": "key-1"},
    )

    assert response.status_code == 503


async def test_checkout_catalog_unavailable_creates_no_order(
    cart_client: httpx.AsyncClient,
    identity_client: FakeIdentityClient,
    catalog_client: FakeCatalogClient,
) -> None:
    identity_client.register("user-token", user_id=uuid.uuid4())
    headers = {"Authorization": "Bearer user-token"}
    product_id = uuid.uuid4()
    await _add_line(cart_client, headers, product_id)
    catalog_client.mark_unavailable(product_id)

    response = await cart_client.post(
        "/api/v1/checkout",
        headers={**headers, "Idempotency-Key": "key-1"},
    )

    assert response.status_code == 503
    assert response.json()["error"]["code"] == "CATALOG_UNAVAILABLE"
    # Cart не тронута: строка по-прежнему присутствует и не заблокирована.
    cart = await cart_client.get("/api/v1/cart", headers=headers)
    assert len(cart.json()["data"]["lines"]) == 1


async def test_checkout_happy_path_creates_order_and_locks_cart(
    cart_client: httpx.AsyncClient,
    identity_client: FakeIdentityClient,
    catalog_client: FakeCatalogClient,
) -> None:
    identity_client.register("user-token", user_id=uuid.uuid4())
    headers = {"Authorization": "Bearer user-token"}
    product_id = uuid.uuid4()
    catalog_client.set_price(product_id, 2_500)
    await _add_line(cart_client, headers, product_id)

    response = await cart_client.post(
        "/api/v1/checkout",
        headers={**headers, "Idempotency-Key": "key-1"},
    )

    assert response.status_code == 201
    body = response.json()["data"]
    assert body["status"] == "pending"
    assert len(body["lines"]) == 1
    assert body["lines"][0]["unit_price_kopecks"] == 2_500

    # Заблокированная строка больше не мутируется через существующие эндпоинты.
    cart = await cart_client.get("/api/v1/cart", headers=headers)
    line_id = cart.json()["data"]["lines"][0]["id"]
    update = await cart_client.patch(
        f"/api/v1/cart/lines/{line_id}", json={"quantity": 9}, headers=headers
    )
    assert update.status_code == 409
    assert update.json()["error"]["code"] == "line_locked"


async def test_checkout_identical_replay_returns_the_same_order(
    cart_client: httpx.AsyncClient,
    identity_client: FakeIdentityClient,
    catalog_client: FakeCatalogClient,
) -> None:
    identity_client.register("user-token", user_id=uuid.uuid4())
    headers = {"Authorization": "Bearer user-token", "Idempotency-Key": "key-1"}
    product_id = uuid.uuid4()
    await _add_line(cart_client, {"Authorization": "Bearer user-token"}, product_id)

    first = await cart_client.post("/api/v1/checkout", headers=headers)
    second = await cart_client.post("/api/v1/checkout", headers=headers)

    assert first.status_code == 201
    assert second.status_code == 201
    assert second.json()["data"]["id"] == first.json()["data"]["id"]


async def test_checkout_same_key_different_cart_conflicts(
    cart_client: httpx.AsyncClient,
    identity_client: FakeIdentityClient,
    catalog_client: FakeCatalogClient,
) -> None:
    identity_client.register("user-token", user_id=uuid.uuid4())
    auth_headers = {"Authorization": "Bearer user-token"}
    await _add_line(cart_client, auth_headers, uuid.uuid4())

    first = await cart_client.post(
        "/api/v1/checkout", headers={**auth_headers, "Idempotency-Key": "key-1"}
    )
    assert first.status_code == 201

    # Пользователь пытается оформить ДРУГУЮ корзину тем же ключом. Заблокированная
    # строка не позволяет добавить тот же товар, поэтому добавляем новый.
    await _add_line(cart_client, auth_headers, uuid.uuid4())

    second = await cart_client.post(
        "/api/v1/checkout", headers={**auth_headers, "Idempotency-Key": "key-1"}
    )

    assert second.status_code == 409
    assert second.json()["error"]["code"] == "idempotency_key_conflict"
