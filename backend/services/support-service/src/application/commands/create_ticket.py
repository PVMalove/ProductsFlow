# ruff: noqa: E501
"""Create-ticket command and handler."""

import uuid
from dataclasses import dataclass

from kernel_domain.result import Result

from application.ports import TicketCommandPort
from domain.ticket import Ticket


@dataclass(frozen=True)
class CreateTicketCommand:
    """DTO для создания нового тикета."""

    author_id: uuid.UUID
    subject: str
    first_message: str


class CreateTicketCommandHandler:
    def __init__(self, repository: TicketCommandPort) -> None:
        self._repository = repository

    async def execute(self, command: CreateTicketCommand) -> Result[Ticket]:
        ticket = Ticket.create(
            author_id=command.author_id,
            subject=command.subject,
            first_message=command.first_message,
        )
        created = await self._repository.create(ticket)
        return Result.ok(created)
