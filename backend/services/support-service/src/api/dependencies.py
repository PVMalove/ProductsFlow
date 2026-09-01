from typing import Annotated

from fastapi import Depends

from application.ticket_use_cases import (
    CreateTicket,
    GetTicket,
    ListAdminTickets,
    ListTickets,
)
from infrastructure.db.session import DbSessionDI
from infrastructure.db.ticket_repository import TicketRepository


def get_create_ticket_use_case(session: DbSessionDI) -> CreateTicket:
    return CreateTicket(TicketRepository(session))


CreateTicketDI = Annotated[CreateTicket, Depends(get_create_ticket_use_case)]


def get_ticket_use_case(session: DbSessionDI) -> GetTicket:
    return GetTicket(TicketRepository(session))


def get_list_tickets_use_case(session: DbSessionDI) -> ListTickets:
    return ListTickets(TicketRepository(session))


def get_list_admin_tickets_use_case(session: DbSessionDI) -> ListAdminTickets:
    return ListAdminTickets(TicketRepository(session))


GetTicketDI = Annotated[GetTicket, Depends(get_ticket_use_case)]
ListTicketsDI = Annotated[ListTickets, Depends(get_list_tickets_use_case)]
ListAdminTicketsDI = Annotated[
    ListAdminTickets, Depends(get_list_admin_tickets_use_case)
]
