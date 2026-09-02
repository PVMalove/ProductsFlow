import uuid

from fastapi.testclient import TestClient

from api.dependencies import get_create_ticket_handler
from api.main import app
from application.commands import CreateTicketCommand
from domain.ticket import Ticket
from infrastructure.security.auth import get_required_auth


def test_create_ticket_requires_authentication() -> None:
    with TestClient(app) as client:
        response = client.post(
            "/api/v1/tickets",
            json={"subject": "Subject", "first_message": "Message"},
        )

    assert response.status_code == 401


def test_create_ticket_rejects_invalid_token() -> None:
    with TestClient(app) as client:
        response = client.post(
            "/api/v1/tickets",
            headers={"Authorization": "Bearer definitely-invalid"},
            json={"subject": "Subject", "first_message": "Message"},
        )

    assert response.status_code == 401


def test_create_ticket_returns_created_resource() -> None:
    author_id = uuid.uuid4()

    class FakeHandler:
        async def execute(self, command: CreateTicketCommand) -> Ticket:
            return Ticket.create(
                author_id=command.author_id,
                subject=command.subject,
                first_message=command.first_message,
            )

    app.dependency_overrides[get_required_auth] = lambda: author_id
    app.dependency_overrides[get_create_ticket_handler] = lambda: FakeHandler()
    try:
        with TestClient(app) as client:
            response = client.post(
                "/api/v1/tickets",
                json={"subject": "  Subject  ", "first_message": "  Message  "},
            )
    finally:
        app.dependency_overrides.clear()

    assert response.status_code == 201
    assert response.json()["author_id"] == str(author_id)
    assert response.json()["subject"] == "Subject"
    assert response.json()["messages"][0]["body"] == "Message"
