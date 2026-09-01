import uuid

from domain.repositories import TicketRepository
from domain.ticket import Ticket


class CreateTicket:
    def __init__(self, repository: TicketRepository) -> None:
        self._repository = repository

    async def execute(
        self, *, author_id: uuid.UUID, subject: str, first_message: str
    ) -> Ticket:
        ticket = Ticket.create(
            author_id=author_id, subject=subject, first_message=first_message
        )
        return await self._repository.create(ticket)
