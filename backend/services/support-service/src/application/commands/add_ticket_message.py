import uuid
from dataclasses import dataclass

from application.errors import TicketNotFoundError
from application.ports import TicketMutationPort
from domain.ticket import Ticket


@dataclass(frozen=True)
class AddTicketMessageCommand:
    ticket_id: uuid.UUID
    actor_id: uuid.UUID
    body: str
    is_admin: bool = False


class AddTicketMessageCommandHandler:
    def __init__(self, repository: TicketMutationPort) -> None:
        self._repository = repository

    async def handle(self, command: AddTicketMessageCommand) -> Ticket:
        ticket = await self._repository.add_message(
            ticket_id=command.ticket_id,
            actor_id=command.actor_id,
            body=command.body,
            is_admin=command.is_admin,
        )
        if ticket is None:
            raise TicketNotFoundError
        return ticket
