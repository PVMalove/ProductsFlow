"""Get-ticket-detail query and handler (ADR 0033).

One application query returns the ticket together with the first page of
its messages, so the endpoint never orchestrates two handler calls."""

import uuid
from dataclasses import dataclass

from kernel_domain.errors import Error, ErrorType
from kernel_domain.result import Result

from application.ports import TicketQueryPort
from contracts.ticket import TicketDetailView
from domain.repositories import Cursor, PageInfo
from domain.value_objects.ticket_id import TicketId


@dataclass(frozen=True)
class GetTicketDetailQuery:
    ticket_id: TicketId
    actor_id: uuid.UUID
    is_admin: bool
    limit: int
    after: Cursor | None = None
    before: Cursor | None = None
    # Set by the admin-only detail route (`GET /tickets/admin/{id}`) — the
    # owner-or-admin route leaves this `False` and keeps its existing
    # fallback-to-owner behavior.
    require_admin: bool = False


@dataclass(frozen=True)
class TicketDetail:
    """Handler-internal composite: `view` is the JSON-facing payload, while
    `messages_page_info` stays out of it — the router places it in the root
    `meta` instead (ADR 0033), never nested under `data`."""

    view: TicketDetailView
    messages_page_info: PageInfo


class GetTicketDetailQueryHandler:
    def __init__(self, tickets: TicketQueryPort) -> None:
        self._tickets = tickets

    async def execute(self, query: GetTicketDetailQuery) -> Result[TicketDetail]:
        if query.require_admin and not query.is_admin:
            return Result[TicketDetail].fail(
                Error(
                    code="FORBIDDEN",
                    description="Доступ только для администраторов!",
                    type=ErrorType.FORBIDDEN,
                )
            )
        ticket = (
            await self._tickets.get_by_id(query.ticket_id)
            if query.is_admin
            else await self._tickets.get_for_author(query.ticket_id, query.actor_id)
        )
        if ticket is None:
            return Result[TicketDetail].fail(
                Error(
                    code="TICKET_NOT_FOUND",
                    description="Тикет не найден",
                    type=ErrorType.NOT_FOUND,
                )
            )
        page = await self._tickets.list_messages(
            ticket_id=query.ticket_id,
            limit=query.limit,
            after=query.after,
            before=query.before,
        )
        return Result[TicketDetail].ok(
            TicketDetail(
                view=TicketDetailView.from_domain(ticket, page.items),
                messages_page_info=page.page_info,
            )
        )
