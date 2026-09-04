# ruff: noqa: E501
"""Create-ticket command and handler."""

import uuid
from dataclasses import dataclass

from kernel_domain.result import Result

from contracts.ticket import TicketDetailView
from domain.ticket import Ticket
from domain.unit_of_work import SupportUnitOfWork


@dataclass(frozen=True)
class CreateTicketCommand:
    """DTO для создания нового тикета."""

    author_id: uuid.UUID
    subject: str
    first_message: str


class CreateTicketCommandHandler:
    def __init__(self, uow: SupportUnitOfWork) -> None:
        self._uow = uow

    async def execute(self, command: CreateTicketCommand) -> Result[TicketDetailView]:
        ticket = Ticket.create(
            author_id=command.author_id,
            subject=command.subject,
            first_message=command.first_message,
        )
        async with self._uow:
            created = await self._uow.tickets.create(ticket)
            await self._uow.commit()
        return Result[TicketDetailView].ok(
            TicketDetailView.from_domain(created, created.messages)
        )
