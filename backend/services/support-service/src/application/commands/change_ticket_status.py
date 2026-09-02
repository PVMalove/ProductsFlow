import uuid
from dataclasses import dataclass

from application.errors import TicketNotFoundError
from application.ports import TicketMutationPort
from domain.ticket import Ticket, TicketStatus


@dataclass(frozen=True)
class ChangeTicketStatusCommand:
    ticket_id: uuid.UUID
    actor_id: uuid.UUID
    status: TicketStatus


class ChangeTicketStatusCommandHandler:
    def __init__(self, repository: TicketMutationPort) -> None:
        self._repository = repository

    async def handle(self, command: ChangeTicketStatusCommand) -> Ticket:
        ticket = await self._repository.change_status(
            ticket_id=command.ticket_id,
            actor_id=command.actor_id,
            status=command.status,
        )
        if ticket is None:
            raise TicketNotFoundError
        return ticket
