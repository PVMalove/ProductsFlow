from typing import Annotated

from fastapi import Depends

from application.commands import (
    AddTicketMessageCommandHandler,
    ChangeTicketStatusCommandHandler,
    CreateTicketCommandHandler,
    DeleteTicketMessageCommandHandler,
    EditTicketMessageCommandHandler,
)
from application.queries import (
    GetTicketDetailQueryHandler,
    ListAdminTicketsQueryHandler,
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


def get_edit_ticket_message_handler(
    session: DbSessionDI,
) -> EditTicketMessageCommandHandler:
    return EditTicketMessageCommandHandler(TicketRepository(session))


EditTicketMessageDI = Annotated[
    EditTicketMessageCommandHandler, Depends(get_edit_ticket_message_handler)
]


def get_delete_ticket_message_handler(
    session: DbSessionDI,
) -> DeleteTicketMessageCommandHandler:
    return DeleteTicketMessageCommandHandler(TicketRepository(session))


DeleteTicketMessageDI = Annotated[
    DeleteTicketMessageCommandHandler, Depends(get_delete_ticket_message_handler)
]


def get_ticket_detail_handler(session: DbSessionDI) -> GetTicketDetailQueryHandler:
    return GetTicketDetailQueryHandler(TicketRepository(session))


GetTicketDetailDI = Annotated[
    GetTicketDetailQueryHandler, Depends(get_ticket_detail_handler)
]


def get_list_tickets_handler(session: DbSessionDI) -> ListTicketsQueryHandler:
    return ListTicketsQueryHandler(TicketRepository(session))


def get_list_admin_tickets_handler(
    session: DbSessionDI,
) -> ListAdminTicketsQueryHandler:
    return ListAdminTicketsQueryHandler(TicketRepository(session))


ListTicketsDI = Annotated[ListTicketsQueryHandler, Depends(get_list_tickets_handler)]
ListAdminTicketsDI = Annotated[
    ListAdminTicketsQueryHandler, Depends(get_list_admin_tickets_handler)
]
