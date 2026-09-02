from typing import Annotated

from fastapi import Depends

from application.commands import CreateTicketCommandHandler
from application.queries import (
    GetTicketQueryHandler,
    ListAdminTicketsQueryHandler,
    ListTicketMessagesQueryHandler,
    ListTicketsQueryHandler,
)
from infrastructure.db.session import DbSessionDI
from infrastructure.db.ticket_repository import TicketRepository


def get_create_ticket_use_case(session: DbSessionDI) -> CreateTicketCommandHandler:
    return CreateTicketCommandHandler(TicketRepository(session))


CreateTicketDI = Annotated[
    CreateTicketCommandHandler, Depends(get_create_ticket_use_case)
]


def get_ticket_use_case(session: DbSessionDI) -> GetTicketQueryHandler:
    return GetTicketQueryHandler(TicketRepository(session))


def get_list_tickets_use_case(session: DbSessionDI) -> ListTicketsQueryHandler:
    return ListTicketsQueryHandler(TicketRepository(session))


def get_list_admin_tickets_use_case(
    session: DbSessionDI,
) -> ListAdminTicketsQueryHandler:
    return ListAdminTicketsQueryHandler(TicketRepository(session))


def get_list_ticket_messages_use_case(
    session: DbSessionDI,
) -> ListTicketMessagesQueryHandler:
    return ListTicketMessagesQueryHandler(TicketRepository(session))


GetTicketDI = Annotated[GetTicketQueryHandler, Depends(get_ticket_use_case)]
ListTicketsDI = Annotated[ListTicketsQueryHandler, Depends(get_list_tickets_use_case)]
ListAdminTicketsDI = Annotated[
    ListAdminTicketsQueryHandler, Depends(get_list_admin_tickets_use_case)
]
ListTicketMessagesDI = Annotated[
    ListTicketMessagesQueryHandler, Depends(get_list_ticket_messages_use_case)
]
