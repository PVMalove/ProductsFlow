import uuid
from dataclasses import dataclass

from application.errors import TicketNotFoundError
from application.ports import TicketMutationPort
from domain.ticket import Ticket


@dataclass(frozen=True)
class DeleteTicketMessageCommand:
    ticket_id: uuid.UUID
    message_id: uuid.UUID
    actor_id: uuid.UUID
    is_admin: bool = False


class DeleteTicketMessageCommandHandler:
    def __init__(self, repository: TicketMutationPort) -> None:
        self._repository = repository

    async def execute(self, command: DeleteTicketMessageCommand) -> Ticket:
        ticket = await self._repository.delete_message(
            ticket_id=command.ticket_id,
            message_id=command.message_id,
            actor_id=command.actor_id,
            is_admin=command.is_admin,
        )
        if ticket is None:
            raise TicketNotFoundError
        return ticket
