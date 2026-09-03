import uuid

from fastapi.testclient import TestClient
from kernel_domain.errors import Error, ErrorType
from kernel_domain.result import Result
from kernel_platform.security import Actor, ActorRole

from api.dependencies import (
    get_add_ticket_message_handler,
    get_change_ticket_status_handler,
    get_delete_ticket_message_handler,
    get_edit_ticket_message_handler,
    get_list_admin_tickets_handler,
    get_list_tickets_handler,
    get_ticket_detail_handler,
)
from api.main import app
from application.commands import (
    AddTicketMessageCommand,
    ChangeTicketStatusCommand,
    DeleteTicketMessageCommand,
    EditTicketMessageCommand,
)
from application.queries import (
    GetTicketDetailQuery,
    ListAdminTicketsQuery,
    ListTicketsQuery,
    TicketDetail,
)
from contracts.ticket import TicketDetailView
from domain.repositories import PageInfo, TicketPage
from domain.ticket import Ticket, TicketStatus
from infrastructure.security.auth import get_current_actor


def _actor(user_id: uuid.UUID, *, admin: bool = False) -> Actor:
    return Actor(id=user_id, role=ActorRole.ADMIN if admin else ActorRole.USER)


def test_ticket_list_returns_the_callers_page() -> None:
    author_id = uuid.uuid4()
    ticket = Ticket.create(author_id=author_id, subject="Mine", first_message="Body")

    class FakeHandler:
        async def execute(self, query: ListTicketsQuery) -> TicketPage:
            assert query.author_id == author_id
            return TicketPage([ticket], PageInfo("next", None, True, False))

    app.dependency_overrides[get_current_actor] = lambda: _actor(author_id)
    app.dependency_overrides[get_list_tickets_handler] = lambda: FakeHandler()
    try:
        with TestClient(app) as client:
            response = client.get("/api/v1/tickets")
    finally:
        app.dependency_overrides.clear()

    assert response.status_code == 200
    body = response.json()
    assert body["data"][0]["subject"] == "Mine"
    assert body["meta"]["next_cursor"] == "next"


def test_ticket_detail_is_404_when_not_owned_by_the_caller() -> None:
    class FakeHandler:
        async def execute(self, query: GetTicketDetailQuery) -> Result[TicketDetail]:
            return Result.fail(
                Error(
                    code="TICKET_NOT_FOUND",
                    description="Тикет не найден",
                    type=ErrorType.NOT_FOUND,
                )
            )

    app.dependency_overrides[get_current_actor] = lambda: _actor(uuid.uuid4())
    app.dependency_overrides[get_ticket_detail_handler] = lambda: FakeHandler()
    try:
        with TestClient(app) as client:
            response = client.get(f"/api/v1/tickets/{uuid.uuid4()}")
    finally:
        app.dependency_overrides.clear()

    assert response.status_code == 404
    assert response.json()["error"]["code"] == "TICKET_NOT_FOUND"


def test_ticket_detail_reads_messages_through_one_combined_query() -> None:
    author_id = uuid.uuid4()
    ticket = Ticket.create(author_id=author_id, subject="Mine", first_message="Body")

    class FakeHandler:
        async def execute(self, query: GetTicketDetailQuery) -> Result[TicketDetail]:
            return Result.ok(
                TicketDetail(
                    view=TicketDetailView.from_domain(ticket, ticket.messages),
                    messages_page_info=PageInfo(None, None, False, False),
                )
            )

    app.dependency_overrides[get_current_actor] = lambda: _actor(author_id)
    app.dependency_overrides[get_ticket_detail_handler] = lambda: FakeHandler()
    try:
        with TestClient(app) as client:
            response = client.get(f"/api/v1/tickets/{ticket.id}")
    finally:
        app.dependency_overrides.clear()

    assert response.status_code == 200
    body = response.json()
    assert body["data"]["messages"][0]["body"] == "Body"
    assert body["meta"] == {
        "next_cursor": None,
        "prev_cursor": None,
        "has_more": False,
        "has_prev": False,
    }


def test_admin_ticket_list_is_available_through_admin_dependency() -> None:
    class FakeHandler:
        async def execute(self, query: ListAdminTicketsQuery) -> TicketPage:
            return TicketPage([], PageInfo(None, None, False, False))

    app.dependency_overrides[get_current_actor] = lambda: _actor(
        uuid.uuid4(), admin=True
    )
    app.dependency_overrides[get_list_admin_tickets_handler] = lambda: FakeHandler()
    try:
        with TestClient(app) as client:
            response = client.get("/api/v1/tickets/admin")
    finally:
        app.dependency_overrides.clear()

    assert response.status_code == 200


def test_non_admin_cannot_reach_the_admin_ticket_list() -> None:
    app.dependency_overrides[get_current_actor] = lambda: _actor(uuid.uuid4())
    try:
        with TestClient(app) as client:
            response = client.get("/api/v1/tickets/admin")
    finally:
        app.dependency_overrides.clear()

    assert response.status_code == 403
    assert response.json()["error"]["code"] == "FORBIDDEN"


def test_ticket_message_endpoint_passes_owner_or_admin_context() -> None:
    author_id = uuid.uuid4()
    ticket = Ticket.create(author_id=author_id, subject="Mine", first_message="Body")

    class FakeHandler:
        async def execute(self, command: AddTicketMessageCommand) -> Result[Ticket]:
            assert command.ticket_id == ticket.id
            assert command.actor_id == author_id
            assert command.is_admin is False
            return Result.ok(ticket)

    app.dependency_overrides[get_current_actor] = lambda: _actor(author_id)
    app.dependency_overrides[get_add_ticket_message_handler] = lambda: FakeHandler()
    try:
        with TestClient(app) as client:
            response = client.post(
                f"/api/v1/tickets/{ticket.id}/messages", json={"body": "Reply"}
            )
    finally:
        app.dependency_overrides.clear()

    assert response.status_code == 201
    assert response.json()["data"]["subject"] == "Mine"


def test_admin_status_endpoint_passes_status_command() -> None:
    ticket = Ticket.create(
        author_id=uuid.uuid4(), subject="Subject", first_message="First message"
    )
    admin_id = uuid.uuid4()

    class FakeHandler:
        async def execute(self, command: ChangeTicketStatusCommand) -> Result[Ticket]:
            assert command.ticket_id == ticket.id
            assert command.actor_id == admin_id
            assert command.status is TicketStatus.IN_PROGRESS
            return Result.ok(ticket)

    app.dependency_overrides[get_current_actor] = lambda: _actor(admin_id, admin=True)
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


def test_ticket_message_edit_endpoint_passes_message_command() -> None:
    author_id = uuid.uuid4()
    ticket = Ticket.create(author_id=author_id, subject="Mine", first_message="Body")
    message_id = ticket.messages[0].id

    class FakeHandler:
        async def execute(self, command: EditTicketMessageCommand) -> Result[Ticket]:
            assert command.ticket_id == ticket.id
            assert command.message_id == message_id
            assert command.actor_id == author_id
            assert command.body == "Corrected"
            assert command.is_admin is True
            return Result.ok(ticket)

    app.dependency_overrides[get_current_actor] = lambda: _actor(author_id, admin=True)
    app.dependency_overrides[get_edit_ticket_message_handler] = lambda: FakeHandler()
    try:
        with TestClient(app) as client:
            response = client.patch(
                f"/api/v1/tickets/{ticket.id}/messages/{message_id}",
                json={"body": "Corrected"},
            )
    finally:
        app.dependency_overrides.clear()

    assert response.status_code == 200


def test_ticket_message_delete_endpoint_returns_null_data() -> None:
    actor_id = uuid.uuid4()
    ticket = Ticket.create(
        author_id=uuid.uuid4(), subject="Subject", first_message="First message"
    )
    message_id = ticket.messages[0].id

    class FakeHandler:
        async def execute(self, command: DeleteTicketMessageCommand) -> Result[Ticket]:
            assert command.ticket_id == ticket.id
            assert command.message_id == message_id
            assert command.actor_id == actor_id
            assert command.is_admin is True
            return Result.ok(ticket)

    app.dependency_overrides[get_current_actor] = lambda: _actor(actor_id, admin=True)
    app.dependency_overrides[get_delete_ticket_message_handler] = lambda: FakeHandler()
    try:
        with TestClient(app) as client:
            response = client.delete(
                f"/api/v1/tickets/{ticket.id}/messages/{message_id}"
            )
    finally:
        app.dependency_overrides.clear()

    assert response.status_code == 200
    assert response.json() == {"data": None, "meta": {}}


def test_ticket_message_edit_maps_a_closed_ticket_to_conflict() -> None:
    author_id = uuid.uuid4()
    ticket = Ticket.create(author_id=author_id, subject="Mine", first_message="Body")
    message_id = ticket.messages[0].id

    class FakeHandler:
        async def execute(self, command: EditTicketMessageCommand) -> Result[Ticket]:
            return Result.fail(
                Error(
                    code="TICKET_MESSAGE_IMMUTABLE",
                    description="Сообщение нельзя изменить",
                    type=ErrorType.CONFLICT,
                )
            )

    app.dependency_overrides[get_current_actor] = lambda: _actor(author_id)
    app.dependency_overrides[get_edit_ticket_message_handler] = lambda: FakeHandler()
    try:
        with TestClient(app) as client:
            response = client.patch(
                f"/api/v1/tickets/{ticket.id}/messages/{message_id}",
                json={"body": "Corrected"},
            )
    finally:
        app.dependency_overrides.clear()

    assert response.status_code == 409
    assert response.json()["error"]["code"] == "TICKET_MESSAGE_IMMUTABLE"
