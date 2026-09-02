"""Create-ticket command and handler."""

import uuid
from dataclasses import dataclass

from application.ports import TicketCommandPort
from domain.ticket import Ticket


@dataclass(frozen=True)
class CreateTicketCommand:
    author_id: uuid.UUID
    subject: str
    first_message: str


class CreateTicketCommandHandler:
    def __init__(self, repository: TicketCommandPort) -> None:
        self._repository = repository

    async def handle(self, command: CreateTicketCommand) -> Ticket:
        ticket = Ticket.create(
            author_id=command.author_id,
            subject=command.subject,
            first_message=command.first_message,
        )
        return await self._repository.create(ticket)
