"""Публичный query-side интерфейс для application use case'ов support."""

from application.queries.get_ticket import GetTicketQuery, GetTicketQueryHandler
from application.queries.get_ticket_detail import (
    GetTicketDetailQuery,
    GetTicketDetailQueryHandler,
    TicketDetail,
)
from application.queries.list_admin_tickets import (
    ListAdminTicketsQuery,
    ListAdminTicketsQueryHandler,
)
from application.queries.list_ticket_messages import (
    ListTicketMessagesQuery,
    ListTicketMessagesQueryHandler,
)
from application.queries.list_tickets import ListTicketsQuery, ListTicketsQueryHandler

__all__ = [
    "GetTicketDetailQuery",
    "GetTicketDetailQueryHandler",
    "GetTicketQuery",
    "GetTicketQueryHandler",
    "ListAdminTicketsQuery",
    "ListAdminTicketsQueryHandler",
    "ListTicketMessagesQuery",
    "ListTicketMessagesQueryHandler",
    "ListTicketsQuery",
    "ListTicketsQueryHandler",
    "TicketDetail",
]
