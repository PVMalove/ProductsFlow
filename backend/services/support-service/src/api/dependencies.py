from typing import Annotated

from fastapi import Depends

from application.commands import (
    AddTicketMessageCommandHandler,
    ChangeTicketStatusCommandHandler,
    CreateTicketCommandHandler,
)
from application.queries import (
    GetTicketQueryHandler,
    ListAdminTicketsQueryHandler,
    ListTicketMessagesQueryHandler,
    ListTicketsQueryHandler,
)
from infrastructure.db.session import DbSessionDI
from infrastructure.db.ticket_repository import TicketRepository


def get_create_ticket_handler(session: DbSessionDI) -> CreateTicketCommandHandler:
    return CreateTicketCommandHandler(TicketRepository(session))


CreateTicketDI = Annotated[
    CreateTicketCommandHandler, Depends(get_create_ticket_handler)
]


def get_add_ticket_message_handler(
    session: DbSessionDI,
) -> AddTicketMessageCommandHandler:
    return AddTicketMessageCommandHandler(TicketRepository(session))


AddTicketMessageDI = Annotated[
    AddTicketMessageCommandHandler, Depends(get_add_ticket_message_handler)
]


def get_change_ticket_status_handler(
    session: DbSessionDI,
) -> ChangeTicketStatusCommandHandler:
    return ChangeTicketStatusCommandHandler(TicketRepository(session))


ChangeTicketStatusDI = Annotated[
    ChangeTicketStatusCommandHandler, Depends(get_change_ticket_status_handler)
]


def get_ticket_handler(session: DbSessionDI) -> GetTicketQueryHandler:
    return GetTicketQueryHandler(TicketRepository(session))


def get_list_tickets_handler(session: DbSessionDI) -> ListTicketsQueryHandler:
    return ListTicketsQueryHandler(TicketRepository(session))


def get_list_admin_tickets_handler(
    session: DbSessionDI,
) -> ListAdminTicketsQueryHandler:
    return ListAdminTicketsQueryHandler(TicketRepository(session))


def get_list_ticket_messages_handler(
    session: DbSessionDI,
) -> ListTicketMessagesQueryHandler:
    return ListTicketMessagesQueryHandler(TicketRepository(session))


GetTicketDI = Annotated[GetTicketQueryHandler, Depends(get_ticket_handler)]
ListTicketsDI = Annotated[ListTicketsQueryHandler, Depends(get_list_tickets_handler)]
ListAdminTicketsDI = Annotated[
    ListAdminTicketsQueryHandler, Depends(get_list_admin_tickets_handler)
]
ListTicketMessagesDI = Annotated[
    ListTicketMessagesQueryHandler, Depends(get_list_ticket_messages_handler)
]
