import uuid

from fastapi.testclient import TestClient
from kernel_domain.result import Result
from kernel_platform.security import Actor, ActorRole

from api.dependencies import get_create_ticket_handler
from api.main import app
from application.commands import CreateTicketCommand
from contracts.ticket import TicketDetailView
from domain.entities.ticket import Ticket
from infrastructure.security.auth import get_current_actor


def test_create_ticket_requires_authentication() -> None:
    with TestClient(app) as client:
        response = client.post(
            "/api/v1/tickets",
            json={"subject": "Subject", "first_message": "Message"},
        )

    assert response.status_code == 401
    assert response.json()["error"]["code"] == "UNAUTHORIZED"


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
        async def execute(
            self, command: CreateTicketCommand
        ) -> Result[TicketDetailView]:
            ticket = Ticket.create(
                author_id=command.author_id,
                subject=command.subject,
                first_message=command.first_message,
            )
            return Result[TicketDetailView].ok(
                TicketDetailView.from_domain(ticket, ticket.messages)
            )

    app.dependency_overrides[get_current_actor] = lambda: Actor(
        id=author_id, role=ActorRole.USER
    )
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
    body = response.json()["data"]
    assert body["author_id"] == str(author_id)
    assert body["subject"] == "Subject"
    assert body["messages"][0]["body"] == "Message"
