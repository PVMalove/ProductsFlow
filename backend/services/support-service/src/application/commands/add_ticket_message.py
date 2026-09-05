import uuid
from dataclasses import dataclass

from kernel_domain.result import Result

from contracts.ticket import TicketView
from domain.entities.ticket import TicketClosedError, TicketMessageInvalidBodyError
from domain.errors import SupportErrors
from domain.unit_of_work import SupportUnitOfWork
from domain.value_objects.ticket_id import TicketId


@dataclass(frozen=True)
class AddTicketMessageCommand:
    """DTO для добавления сообщения в тикет."""

    ticket_id: TicketId
    actor_id: uuid.UUID
    body: str
    is_admin: bool = False


class AddTicketMessageCommandHandler:
    def __init__(self, uow: SupportUnitOfWork) -> None:
        self._uow = uow

    async def execute(self, command: AddTicketMessageCommand) -> Result[TicketView]:
        async with self._uow:
            try:
                ticket = await self._uow.tickets.add_message(
                    ticket_id=command.ticket_id,
                    actor_id=command.actor_id,
                    body=command.body,
                    is_admin=command.is_admin,
                )
            except TicketClosedError:
                return Result[TicketView].fail(SupportErrors.ticket_closed_conflict())
            except TicketMessageInvalidBodyError:
                return Result[TicketView].fail(SupportErrors.invalid_body())
            if ticket is None:
                return Result[TicketView].fail(SupportErrors.ticket_not_found())
            await self._uow.commit()
        return Result[TicketView].ok(TicketView.from_domain(ticket))
