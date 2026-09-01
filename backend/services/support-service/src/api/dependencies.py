from typing import Annotated

from fastapi import Depends

from application.ticket_use_cases import CreateTicket
from infrastructure.db.session import DbSessionDI
from infrastructure.db.ticket_repository import TicketRepository


def get_create_ticket_use_case(session: DbSessionDI) -> CreateTicket:
    return CreateTicket(TicketRepository(session))


CreateTicketDI = Annotated[CreateTicket, Depends(get_create_ticket_use_case)]
