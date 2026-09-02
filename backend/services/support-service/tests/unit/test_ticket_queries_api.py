import uuid

from fastapi.testclient import TestClient

from api.dependencies import (
    get_list_admin_tickets_use_case,
    get_list_ticket_messages_use_case,
    get_list_tickets_use_case,
    get_ticket_use_case,
)
from api.main import app
from application.queries import (
    GetTicketQuery,
    ListAdminTicketsQuery,
    ListTicketsQuery,
)
from domain.repositories import MessagePage, PageInfo, TicketPage
from domain.ticket import Ticket
from infrastructure.security.auth import get_admin_auth, get_required_auth


def test_ticket_list_returns_the_callers_page() -> None:
    author_id = uuid.uuid4()
    ticket = Ticket.create(author_id=author_id, subject="Mine", first_message="Body")

    class FakeUseCase:
        async def handle(self, query: ListTicketsQuery) -> TicketPage:
            assert query.author_id == author_id
            return TicketPage([ticket], PageInfo("next", None, True, False))

    app.dependency_overrides[get_required_auth] = lambda: author_id
    app.dependency_overrides[get_list_tickets_use_case] = lambda: FakeUseCase()
    try:
        with TestClient(app) as client:
            response = client.get("/api/v1/tickets")
    finally:
        app.dependency_overrides.clear()

    assert response.status_code == 200
    assert response.json()["items"][0]["subject"] == "Mine"
    assert response.json()["page_info"]["next_cursor"] == "next"


def test_ticket_detail_is_404_when_not_owned_by_the_caller() -> None:
    class FakeUseCase:
        async def handle(self, query: GetTicketQuery) -> None:
            return None

    app.dependency_overrides[get_required_auth] = lambda: uuid.uuid4()
    app.dependency_overrides[get_ticket_use_case] = lambda: FakeUseCase()
    app.dependency_overrides[get_list_ticket_messages_use_case] = lambda: object()
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
        async def handle(self, query: GetTicketQuery) -> Ticket:
            return ticket

    class FakeMessageQuery:
        async def handle(self, query: object) -> MessagePage:
            return MessagePage(ticket.messages, PageInfo(None, None, False, False))

    app.dependency_overrides[get_required_auth] = lambda: author_id
    app.dependency_overrides[get_ticket_use_case] = lambda: FakeTicketQuery()
    app.dependency_overrides[get_list_ticket_messages_use_case] = lambda: (
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
    class FakeUseCase:
        async def handle(self, query: ListAdminTicketsQuery) -> TicketPage:
            return TicketPage([], PageInfo(None, None, False, False))

    app.dependency_overrides[get_admin_auth] = lambda: uuid.uuid4()
    app.dependency_overrides[get_list_admin_tickets_use_case] = lambda: FakeUseCase()
    try:
        with TestClient(app) as client:
            response = client.get("/api/v1/tickets/admin")
    finally:
        app.dependency_overrides.clear()

    assert response.status_code == 200
