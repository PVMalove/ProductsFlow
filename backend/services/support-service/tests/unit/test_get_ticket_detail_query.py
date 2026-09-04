import uuid

from application.queries.get_ticket_detail import (
    GetTicketDetailQuery,
    GetTicketDetailQueryHandler,
)
from domain.entities.ticket import Ticket
from domain.repositories import Cursor, MessagePage, PageInfo, TicketPage
from domain.value_objects.ticket_id import TicketId


class _FakeTicketQueryPort:
    def __init__(self, ticket: Ticket) -> None:
        self._ticket = ticket

    async def get_by_id(self, ticket_id: TicketId) -> Ticket | None:
        return self._ticket if ticket_id == self._ticket.id else None

    async def get_for_author(
        self, ticket_id: TicketId, author_id: uuid.UUID
    ) -> Ticket | None:
        raise AssertionError("require_admin must not fall back to owner lookup")

    async def list_for_author(
        self,
        *,
        author_id: uuid.UUID,
        limit: int,
        after: Cursor | None = None,
        before: Cursor | None = None,
    ) -> TicketPage:
        raise NotImplementedError

    async def list_all(
        self,
        *,
        limit: int,
        after: Cursor | None = None,
        before: Cursor | None = None,
    ) -> TicketPage:
        raise NotImplementedError

    async def list_messages(
        self,
        *,
        ticket_id: TicketId,
        limit: int,
        after: Cursor | None = None,
        before: Cursor | None = None,
    ) -> MessagePage:
        return MessagePage(self._ticket.messages, PageInfo(None, None, False, False))


def _ticket() -> Ticket:
    return Ticket.create(
        author_id=uuid.uuid4(), subject="Subject", first_message="Body"
    ).value


async def test_admin_only_query_rejects_a_non_admin_actor() -> None:
    ticket = _ticket()
    handler = GetTicketDetailQueryHandler(_FakeTicketQueryPort(ticket))

    result = await handler.execute(
        GetTicketDetailQuery(
            ticket_id=ticket.id,
            actor_id=uuid.uuid4(),
            is_admin=False,
            limit=20,
            require_admin=True,
        )
    )

    assert result.is_err
    assert result.error.code == "FORBIDDEN"


async def test_admin_only_query_returns_any_ticket_for_an_admin() -> None:
    ticket = _ticket()
    handler = GetTicketDetailQueryHandler(_FakeTicketQueryPort(ticket))

    result = await handler.execute(
        GetTicketDetailQuery(
            ticket_id=ticket.id,
            actor_id=uuid.uuid4(),
            is_admin=True,
            limit=20,
            require_admin=True,
        )
    )

    assert result.is_ok
    assert result.value.view.id == ticket.id.value
