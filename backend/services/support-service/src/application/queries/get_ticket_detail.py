"""Query и handler get-ticket-detail (ADR 0002).

Один application-query возвращает тикет вместе с первой страницей его
сообщений, поэтому эндпоинт никогда не оркестрирует два вызова handler'а."""

import uuid
from dataclasses import dataclass

from kernel_domain.result import Result

from application.ports import TicketQueryPort
from contracts.ticket import TicketDetailView
from domain.errors import SupportErrors
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
    # Устанавливается admin-only маршрутом деталей (`GET /tickets/admin/{id}`)
    # — маршрут owner-or-admin оставляет это `False` и сохраняет своё
    # существующее поведение fallback-to-owner.
    require_admin: bool = False


@dataclass(frozen=True)
class TicketDetail:
    """Внутренний для handler'а композит: `view` — JSON-facing payload, а
    `messages_page_info` в него не входит — роутер помещает его в корневой
    `meta` (ADR 0002), никогда не вложенным в `data`."""

    view: TicketDetailView
    messages_page_info: PageInfo


class GetTicketDetailQueryHandler:
    def __init__(self, tickets: TicketQueryPort) -> None:
        self._tickets = tickets

    async def execute(self, query: GetTicketDetailQuery) -> Result[TicketDetail]:
        if query.require_admin and not query.is_admin:
            return Result[TicketDetail].fail(SupportErrors.forbidden())
        ticket = (
            await self._tickets.get_by_id(query.ticket_id)
            if query.is_admin
            else await self._tickets.get_for_author(query.ticket_id, query.actor_id)
        )
        if ticket is None:
            return Result[TicketDetail].fail(SupportErrors.ticket_not_found())
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
