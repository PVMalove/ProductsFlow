import uuid
from dataclasses import dataclass

from kernel_domain.result import Result

from contracts.ticket import TicketView
from domain.entities.ticket import (
    InvalidStatusTransitionError,
    TicketClosedError,
)
from domain.errors import SupportErrors
from domain.ticket_status import TicketStatus
from domain.unit_of_work import SupportUnitOfWork
from domain.value_objects.ticket_id import TicketId


@dataclass(frozen=True)
class ChangeTicketStatusCommand:
    """DTO для изменения статуса тикета."""

    ticket_id: TicketId
    actor_id: uuid.UUID
    status: TicketStatus
    is_admin: bool = False


class ChangeTicketStatusCommandHandler:
    def __init__(self, uow: SupportUnitOfWork) -> None:
        self._uow = uow

    async def execute(self, command: ChangeTicketStatusCommand) -> Result[TicketView]:
        if not command.is_admin:
            return Result[TicketView].fail(SupportErrors.forbidden())
        async with self._uow:
            try:
                ticket = await self._uow.tickets.change_status(
                    ticket_id=command.ticket_id,
                    actor_id=command.actor_id,
                    status=command.status,
                )
            except TicketClosedError:
                return Result[TicketView].fail(SupportErrors.ticket_closed_conflict())
            except InvalidStatusTransitionError:
                return Result[TicketView].fail(
                    SupportErrors.ticket_status_transition_rejected()
                )
            if ticket is None:
                return Result[TicketView].fail(SupportErrors.ticket_not_found())
            await self._uow.commit()
        return Result[TicketView].ok(TicketView.from_domain(ticket))
