import uuid
from dataclasses import dataclass

from application.errors import TicketNotFoundError
from application.ports import TicketMutationPort
from domain.ticket import Ticket


@dataclass(frozen=True)
class EditTicketMessageCommand:
    ticket_id: uuid.UUID
    message_id: uuid.UUID
    actor_id: uuid.UUID
    body: str
    is_admin: bool = False


class EditTicketMessageCommandHandler:
    def __init__(self, repository: TicketMutationPort) -> None:
        self._repository = repository

    async def execute(self, command: EditTicketMessageCommand) -> Ticket:
        ticket = await self._repository.edit_message(
            ticket_id=command.ticket_id,
            message_id=command.message_id,
            actor_id=command.actor_id,
            body=command.body,
            is_admin=command.is_admin,
        )
        if ticket is None:
            raise TicketNotFoundError
        return ticket
