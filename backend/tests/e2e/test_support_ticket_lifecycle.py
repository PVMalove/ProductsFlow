import uuid

import httpx
import pytest

from tests.e2e.conftest import login_seeded_admin, register_and_login


@pytest.mark.asyncio
async def test_ticket_lifecycle_authorization_and_moderation_through_gateway(
    gateway_client: httpx.AsyncClient,
) -> None:
    suffix = uuid.uuid4().hex
    owner_token = await register_and_login(
        gateway_client, email=f"e2e-ticket-owner-{suffix}@example.test"
    )
    stranger_token = await register_and_login(
        gateway_client, email=f"e2e-ticket-stranger-{suffix}@example.test"
    )
    owner_headers = {"Authorization": f"Bearer {owner_token}"}
    stranger_headers = {"Authorization": f"Bearer {stranger_token}"}

    created = await gateway_client.post(
        "/api/v1/tickets",
        headers=owner_headers,
        json={
            "subject": f"E2E ticket {suffix}",
            "first_message": "The original problem description.",
        },
    )
    assert created.status_code == 201, created.text
    ticket = created.json()["data"]
    ticket_id = ticket["id"]
    initial_message_id = ticket["messages"][0]["id"]
    assert ticket["status"] == "OPEN"

    hidden_from_stranger = await gateway_client.get(
        f"/api/v1/tickets/{ticket_id}", headers=stranger_headers
    )
    assert hidden_from_stranger.status_code == 404, hidden_from_stranger.text

    stranger_reply = await gateway_client.post(
        f"/api/v1/tickets/{ticket_id}/messages",
        headers=stranger_headers,
        json={"body": "I must not be able to reply here."},
    )
    assert stranger_reply.status_code == 404, stranger_reply.text

    edited = await gateway_client.patch(
        f"/api/v1/tickets/{ticket_id}/messages/{initial_message_id}",
        headers=owner_headers,
        json={"body": "The corrected problem description."},
    )
    assert edited.status_code == 200, edited.text

    admin_token = await login_seeded_admin(gateway_client)
    admin_headers = {"Authorization": f"Bearer {admin_token}"}

    denied_admin_listing = await gateway_client.get(
        "/api/v1/tickets/admin", headers=owner_headers
    )
    assert denied_admin_listing.status_code == 403, denied_admin_listing.text

    admin_reply = await gateway_client.post(
        f"/api/v1/tickets/{ticket_id}/messages",
        headers=admin_headers,
        json={"body": "We are investigating the problem."},
    )
    assert admin_reply.status_code == 201, admin_reply.text

    for expected_status in ("IN_PROGRESS", "RESOLVED"):
        changed = await gateway_client.patch(
            f"/api/v1/tickets/{ticket_id}/status",
            headers=admin_headers,
            json={"status": expected_status},
        )
        assert changed.status_code == 200, changed.text
        assert changed.json()["data"]["status"] == expected_status

    reopened = await gateway_client.post(
        f"/api/v1/tickets/{ticket_id}/messages",
        headers=owner_headers,
        json={"body": "The problem is still happening."},
    )
    assert reopened.status_code == 201, reopened.text
    assert reopened.json()["data"]["status"] == "IN_PROGRESS"

    for expected_status in ("RESOLVED", "CLOSED"):
        changed = await gateway_client.patch(
            f"/api/v1/tickets/{ticket_id}/status",
            headers=admin_headers,
            json={"status": expected_status},
        )
        assert changed.status_code == 200, changed.text
        assert changed.json()["data"]["status"] == expected_status

    reply_to_closed_ticket = await gateway_client.post(
        f"/api/v1/tickets/{ticket_id}/messages",
        headers=owner_headers,
        json={"body": "This must be rejected after closing."},
    )
    assert reply_to_closed_ticket.status_code == 409, reply_to_closed_ticket.text
    assert reply_to_closed_ticket.json()["error"]["code"] == "TICKET_CLOSED"

    moderated = await gateway_client.delete(
        f"/api/v1/tickets/{ticket_id}/messages/{initial_message_id}",
        headers=admin_headers,
    )
    assert moderated.status_code == 200, moderated.text
    assert moderated.json() == {"data": None, "meta": {}}

    detail = await gateway_client.get(
        f"/api/v1/tickets/admin/{ticket_id}", headers=admin_headers
    )
    assert detail.status_code == 200, detail.text
    ticket_detail = detail.json()["data"]
    assert ticket_detail["status"] == "CLOSED"
    initial_message = next(
        message
        for message in ticket_detail["messages"]
        if message["id"] == initial_message_id
    )
    assert initial_message["body"] == "[Сообщение удалено]"
    assert initial_message["is_deleted"] is True
