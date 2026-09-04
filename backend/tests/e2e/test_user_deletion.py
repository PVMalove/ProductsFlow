import uuid

import httpx
import pytest
from tests.e2e.conftest import login_seeded_admin, wait_for_ticket_closed


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
async def test_self_delete_anonymizes_and_closes_the_users_ticket(
    gateway_client: httpx.AsyncClient,
) -> None:
    suffix = uuid.uuid4().hex
    user_token = await _register_and_login(
        gateway_client, email=f"e2e-deleted-user-{suffix}@example.test"
    )
    user_headers = {"Authorization": f"Bearer {user_token}"}

    created = await gateway_client.post(
        "/api/v1/tickets",
        headers=user_headers,
        json={
            "subject": f"E2E deletion ticket {suffix}",
            "first_message": "Please help with my account.",
        },
    )
    assert created.status_code == 201, created.text
    ticket = created.json()["data"]
    ticket_id = ticket["id"]
    assert ticket["status"] == "OPEN"

    deleted = await gateway_client.delete("/api/v1/users/me", headers=user_headers)
    assert deleted.status_code == 200, deleted.text
    assert deleted.json() == {"data": None, "meta": {}}

    denied = await gateway_client.get("/api/v1/users/me", headers=user_headers)
    assert denied.status_code == 403, denied.text

    admin_token = await login_seeded_admin(gateway_client)
    admin_headers = {"Authorization": f"Bearer {admin_token}"}

    closed_ticket = await wait_for_ticket_closed(
        gateway_client,
        url=f"/api/v1/tickets/admin/{ticket_id}",
        headers=admin_headers,
    )

    assert closed_ticket["author_id"] is None
    messages = closed_ticket["messages"]
    assert messages[0]["author_id"] is None
    assert any(message["is_system"] for message in messages)
