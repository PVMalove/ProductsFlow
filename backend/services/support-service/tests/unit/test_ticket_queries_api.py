import uuid

from fastapi.testclient import TestClient

from api.dependencies import (
    get_list_admin_tickets_use_case,
    get_list_tickets_use_case,
    get_ticket_use_case,
)
from api.main import app
from domain.repositories import PageInfo, TicketPage
from domain.ticket import Ticket
from infrastructure.security.auth import get_admin_auth, get_required_auth


def test_ticket_list_returns_the_callers_page() -> None:
    author_id = uuid.uuid4()
    ticket = Ticket.create(author_id=author_id, subject="Mine", first_message="Body")

    class FakeUseCase:
        async def execute(self, **kwargs: object) -> TicketPage:
            assert kwargs["author_id"] == author_id
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
        async def execute(self, **kwargs: object) -> None:
            return None

    app.dependency_overrides[get_required_auth] = lambda: uuid.uuid4()
    app.dependency_overrides[get_ticket_use_case] = lambda: FakeUseCase()
    try:
        with TestClient(app) as client:
            response = client.get(f"/api/v1/tickets/{uuid.uuid4()}")
    finally:
        app.dependency_overrides.clear()

    assert response.status_code == 404


def test_admin_ticket_list_is_available_through_admin_dependency() -> None:
    class FakeUseCase:
        async def execute(self, **kwargs: object) -> TicketPage:
            return TicketPage([], PageInfo(None, None, False, False))

    app.dependency_overrides[get_admin_auth] = lambda: uuid.uuid4()
    app.dependency_overrides[get_list_admin_tickets_use_case] = lambda: FakeUseCase()
    try:
        with TestClient(app) as client:
            response = client.get("/api/v1/tickets/admin")
    finally:
        app.dependency_overrides.clear()

    assert response.status_code == 200
