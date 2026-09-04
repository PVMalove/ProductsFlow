# ruff: noqa: E501
import uuid
from dataclasses import dataclass

from kernel_domain.errors import Error, ErrorType
from kernel_domain.result import Result

from contracts.ticket import TicketView
from domain.ticket import (
    InvalidStatusTransitionError,
    TicketClosedError,
    TicketStatus,
)
from domain.unit_of_work import SupportUnitOfWork


@dataclass(frozen=True)
class ChangeTicketStatusCommand:
    """DTO для изменения статуса тикета."""

    ticket_id: uuid.UUID
    actor_id: uuid.UUID
    status: TicketStatus
    is_admin: bool = False


class ChangeTicketStatusCommandHandler:
    def __init__(self, uow: SupportUnitOfWork) -> None:
        self._uow = uow

    async def execute(self, command: ChangeTicketStatusCommand) -> Result[TicketView]:
        if not command.is_admin:
            return Result[TicketView].fail(
                Error(
                    code="FORBIDDEN",
                    description="Доступ только для администраторов!",
                    type=ErrorType.FORBIDDEN,
                )
            )
        async with self._uow:
            try:
                ticket = await self._uow.tickets.change_status(
                    ticket_id=command.ticket_id,
                    actor_id=command.actor_id,
                    status=command.status,
                )
            except TicketClosedError:
                return Result[TicketView].fail(
                    Error(
                        code="TICKET_CLOSED",
                        description="Закрытый тикет нельзя изменять",
                        type=ErrorType.CONFLICT,
                    )
                )
            except InvalidStatusTransitionError:
                return Result[TicketView].fail(
                    Error(
                        code="INVALID_STATUS_TRANSITION",
                        description="Недопустимый переход статуса тикета",
                        type=ErrorType.CONFLICT,
                    )
                )
            if ticket is None:
                return Result[TicketView].fail(
                    Error(
                        code="TICKET_NOT_FOUND",
                        description="Тикет не найден",
                        type=ErrorType.NOT_FOUND,
                    )
                )
            await self._uow.commit()
        return Result[TicketView].ok(TicketView.from_domain(ticket))
