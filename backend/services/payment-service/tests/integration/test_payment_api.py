"""Сквозной HTTP через реальный Postgres + MockPspAdapter (issue #368, Seams
for TDD #7, по образцу inventory's test_inventory_api.py): 401 без токена,
200 для authorize, идемпотентный повтор без повторного обращения к PSP,
конфликт при том же ключе с другим телом, happy-path void/capture, capture
заблокирован новым ключом при CAPTURE_UNKNOWN."""

import uuid

import httpx
import pytest

from tests.integration.conftest import SpyPspAdapter
from tests.integration.fake_identity_client import FakeIdentityClient

pytestmark = pytest.mark.asyncio(loop_scope="session")


async def test_authorize_requires_authentication(
    payment_client: httpx.AsyncClient,
) -> None:
    response = await payment_client.post(
        "/api/v1/payments/authorizations",
        json={"amount": 1000, "payment_method_token": "success"},
        headers={"Idempotency-Key": "key-1"},
    )

    assert response.status_code == 401


async def test_authorize_succeeds_for_any_authenticated_user(
    payment_client: httpx.AsyncClient,
    identity_client: FakeIdentityClient,
) -> None:
    identity_client.register("user-token", user_id=uuid.uuid4(), role="user")

    response = await payment_client.post(
        "/api/v1/payments/authorizations",
        json={"amount": 1000, "payment_method_token": "success"},
        headers={"Idempotency-Key": "key-1", "Authorization": "Bearer user-token"},
    )

    assert response.status_code == 201
    body = response.json()
    assert body["data"]["status"] == "authorized"
    assert body["data"]["amount"] == 1000


async def test_authorize_repeated_idempotency_key_does_not_call_psp_again(
    payment_client: httpx.AsyncClient,
    identity_client: FakeIdentityClient,
    psp_client: SpyPspAdapter,
) -> None:
    identity_client.register("user-token", user_id=uuid.uuid4(), role="user")
    headers = {"Idempotency-Key": "key-2", "Authorization": "Bearer user-token"}
    payload = {"amount": 1500, "payment_method_token": "success"}

    first = await payment_client.post(
        "/api/v1/payments/authorizations", json=payload, headers=headers
    )
    second = await payment_client.post(
        "/api/v1/payments/authorizations", json=payload, headers=headers
    )

    assert first.status_code == 201
    assert second.status_code == 201
    assert first.json()["data"] == second.json()["data"]
    assert len(psp_client.authorize_calls) == 1


async def test_authorize_same_key_different_body_conflicts(
    payment_client: httpx.AsyncClient,
    identity_client: FakeIdentityClient,
) -> None:
    identity_client.register("user-token", user_id=uuid.uuid4(), role="user")
    headers = {"Idempotency-Key": "key-3", "Authorization": "Bearer user-token"}

    first = await payment_client.post(
        "/api/v1/payments/authorizations",
        json={"amount": 1000, "payment_method_token": "success"},
        headers=headers,
    )
    second = await payment_client.post(
        "/api/v1/payments/authorizations",
        json={"amount": 2000, "payment_method_token": "success"},
        headers=headers,
    )

    assert first.status_code == 201
    assert second.status_code == 409
    assert second.json()["error"]["code"] == "idempotency_conflict"


async def test_authorize_unknown_token_returns_400(
    payment_client: httpx.AsyncClient,
    identity_client: FakeIdentityClient,
) -> None:
    identity_client.register("user-token", user_id=uuid.uuid4(), role="user")

    response = await payment_client.post(
        "/api/v1/payments/authorizations",
        json={"amount": 1000, "payment_method_token": "not-a-real-scenario"},
        headers={"Idempotency-Key": "key-4", "Authorization": "Bearer user-token"},
    )

    assert response.status_code == 400
    assert response.json()["error"]["code"] == "unknown_test_scenario_token"


async def test_void_happy_path(
    payment_client: httpx.AsyncClient,
    identity_client: FakeIdentityClient,
) -> None:
    identity_client.register("user-token", user_id=uuid.uuid4(), role="user")
    headers = {"Authorization": "Bearer user-token"}

    authorize_response = await payment_client.post(
        "/api/v1/payments/authorizations",
        json={"amount": 1000, "payment_method_token": "success"},
        headers={**headers, "Idempotency-Key": "key-5"},
    )
    authorization_id = authorize_response.json()["data"]["id"]

    void_response = await payment_client.post(
        f"/api/v1/payments/authorizations/{authorization_id}/void",
        headers={**headers, "Idempotency-Key": "void-key-5"},
    )

    assert void_response.status_code == 200
    assert void_response.json()["data"]["status"] == "voided"


async def test_capture_happy_path(
    payment_client: httpx.AsyncClient,
    identity_client: FakeIdentityClient,
) -> None:
    identity_client.register("user-token", user_id=uuid.uuid4(), role="user")
    headers = {"Authorization": "Bearer user-token"}

    authorize_response = await payment_client.post(
        "/api/v1/payments/authorizations",
        json={"amount": 1000, "payment_method_token": "success"},
        headers={**headers, "Idempotency-Key": "key-6"},
    )
    authorization_id = authorize_response.json()["data"]["id"]

    capture_response = await payment_client.post(
        f"/api/v1/payments/authorizations/{authorization_id}/capture",
        headers={**headers, "Idempotency-Key": "capture-key-6"},
    )

    assert capture_response.status_code == 200
    assert capture_response.json()["data"]["status"] == "captured"


async def test_capture_blocked_by_new_key_after_capture_unknown(
    payment_client: httpx.AsyncClient,
    identity_client: FakeIdentityClient,
) -> None:
    identity_client.register("user-token", user_id=uuid.uuid4(), role="user")
    headers = {"Authorization": "Bearer user-token"}

    authorize_response = await payment_client.post(
        "/api/v1/payments/authorizations",
        json={"amount": 1000, "payment_method_token": "unknown_capture"},
        headers={**headers, "Idempotency-Key": "key-7"},
    )
    authorization_id = authorize_response.json()["data"]["id"]

    first_capture = await payment_client.post(
        f"/api/v1/payments/authorizations/{authorization_id}/capture",
        headers={**headers, "Idempotency-Key": "capture-key-7a"},
    )
    assert first_capture.status_code == 200
    assert first_capture.json()["data"]["status"] == "capture_unknown"

    second_capture = await payment_client.post(
        f"/api/v1/payments/authorizations/{authorization_id}/capture",
        headers={**headers, "Idempotency-Key": "capture-key-7b"},
    )

    assert second_capture.status_code == 409
    assert second_capture.json()["error"]["code"] == "capture_pending_reconciliation"


async def test_lookup_by_idempotency_key(
    payment_client: httpx.AsyncClient,
    identity_client: FakeIdentityClient,
) -> None:
    identity_client.register("user-token", user_id=uuid.uuid4(), role="user")
    headers = {"Authorization": "Bearer user-token"}
    await payment_client.post(
        "/api/v1/payments/authorizations",
        json={"amount": 1000, "payment_method_token": "success"},
        headers={**headers, "Idempotency-Key": "key-8"},
    )

    response = await payment_client.get(
        "/api/v1/payments/lookup/key-8", headers=headers
    )

    assert response.status_code == 200
    assert response.json()["data"]["status"] == "authorized"


async def test_lookup_unknown_key_returns_404(
    payment_client: httpx.AsyncClient,
    identity_client: FakeIdentityClient,
) -> None:
    identity_client.register("user-token", user_id=uuid.uuid4(), role="user")

    response = await payment_client.get(
        "/api/v1/payments/lookup/does-not-exist",
        headers={"Authorization": "Bearer user-token"},
    )

    assert response.status_code == 404
