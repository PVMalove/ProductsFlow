import uuid

from fastapi.testclient import TestClient

from api.dependencies import (
    get_add_ticket_message_handler,
    get_change_ticket_status_handler,
    get_list_admin_tickets_handler,
    get_list_ticket_messages_handler,
    get_list_tickets_handler,
    get_ticket_handler,
)
from api.main import app
from application.commands import AddTicketMessageCommand, ChangeTicketStatusCommand
from application.queries import (
    GetTicketQuery,
    ListAdminTicketsQuery,
    ListTicketsQuery,
)
from domain.repositories import MessagePage, PageInfo, TicketPage
from domain.ticket import Ticket, TicketStatus
from infrastructure.security.auth import get_admin_auth, get_is_admin, get_required_auth


def test_ticket_list_returns_the_callers_page() -> None:
    author_id = uuid.uuid4()
    ticket = Ticket.create(author_id=author_id, subject="Mine", first_message="Body")

    class FakeHandler:
        async def execute(self, query: ListTicketsQuery) -> TicketPage:
            assert query.author_id == author_id
            return TicketPage([ticket], PageInfo("next", None, True, False))

    app.dependency_overrides[get_required_auth] = lambda: author_id
    app.dependency_overrides[get_list_tickets_handler] = lambda: FakeHandler()
    try:
        with TestClient(app) as client:
            response = client.get("/api/v1/tickets")
    finally:
        app.dependency_overrides.clear()

    assert response.status_code == 200
    assert response.json()["items"][0]["subject"] == "Mine"
    assert response.json()["page_info"]["next_cursor"] == "next"


def test_ticket_detail_is_404_when_not_owned_by_the_caller() -> None:
    class FakeHandler:
        async def execute(self, query: GetTicketQuery) -> None:
            return None

    app.dependency_overrides[get_required_auth] = lambda: uuid.uuid4()
    app.dependency_overrides[get_ticket_handler] = lambda: FakeHandler()
    app.dependency_overrides[get_list_ticket_messages_handler] = lambda: object()
    try:
        with TestClient(app) as client:
            response = client.get(f"/api/v1/tickets/{uuid.uuid4()}")
    finally:
        app.dependency_overrides.clear()

    assert response.status_code == 404


def test_ticket_detail_reads_messages_through_a_separate_query_handler() -> None:
    author_id = uuid.uuid4()
    ticket = Ticket.create(author_id=author_id, subject="Mine", first_message="Body")

    class FakeTicketQuery:
        async def execute(self, query: GetTicketQuery) -> Ticket:
            return ticket

    class FakeMessageQuery:
        async def execute(self, query: object) -> MessagePage:
            return MessagePage(ticket.messages, PageInfo(None, None, False, False))

    app.dependency_overrides[get_required_auth] = lambda: author_id
    app.dependency_overrides[get_ticket_handler] = lambda: FakeTicketQuery()
    app.dependency_overrides[get_list_ticket_messages_handler] = lambda: (
        FakeMessageQuery()
    )
    try:
        with TestClient(app) as client:
            response = client.get(f"/api/v1/tickets/{ticket.id}")
    finally:
        app.dependency_overrides.clear()

    assert response.status_code == 200
    assert response.json()["messages"][0]["body"] == "Body"


def test_admin_ticket_list_is_available_through_admin_dependency() -> None:
    class FakeHandler:
        async def execute(self, query: ListAdminTicketsQuery) -> TicketPage:
            return TicketPage([], PageInfo(None, None, False, False))

    app.dependency_overrides[get_admin_auth] = lambda: uuid.uuid4()
    app.dependency_overrides[get_list_admin_tickets_handler] = lambda: FakeHandler()
    try:
        with TestClient(app) as client:
            response = client.get("/api/v1/tickets/admin")
    finally:
        app.dependency_overrides.clear()

    assert response.status_code == 200


def test_ticket_message_endpoint_passes_owner_or_admin_context() -> None:
    author_id = uuid.uuid4()
    ticket = Ticket.create(author_id=author_id, subject="Mine", first_message="Body")

    class FakeHandler:
        async def execute(self, command: AddTicketMessageCommand) -> Ticket:
            assert command.ticket_id == ticket.id
            assert command.actor_id == author_id
            assert command.is_admin is False
            return ticket

    app.dependency_overrides[get_required_auth] = lambda: author_id
    app.dependency_overrides[get_is_admin] = lambda: False
    app.dependency_overrides[get_add_ticket_message_handler] = lambda: FakeHandler()
    try:
        with TestClient(app) as client:
            response = client.post(
                f"/api/v1/tickets/{ticket.id}/messages", json={"body": "Reply"}
            )
    finally:
        app.dependency_overrides.clear()

    assert response.status_code == 201
    assert response.json()["messages"][0]["body"] == "Body"


def test_admin_status_endpoint_passes_status_command() -> None:
    ticket = Ticket.create(
        author_id=uuid.uuid4(), subject="Subject", first_message="First message"
    )
    admin_id = uuid.uuid4()

    class FakeHandler:
        async def execute(self, command: ChangeTicketStatusCommand) -> Ticket:
            assert command.ticket_id == ticket.id
            assert command.actor_id == admin_id
            assert command.status is TicketStatus.IN_PROGRESS
            return ticket

    app.dependency_overrides[get_admin_auth] = lambda: admin_id
    app.dependency_overrides[get_change_ticket_status_handler] = lambda: FakeHandler()
    try:
        with TestClient(app) as client:
            response = client.patch(
                f"/api/v1/tickets/{ticket.id}/status",
                json={"status": "IN_PROGRESS"},
            )
    finally:
        app.dependency_overrides.clear()

    assert response.status_code == 200
