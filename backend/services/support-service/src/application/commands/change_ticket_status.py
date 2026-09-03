# ruff: noqa: E501
import uuid
from dataclasses import dataclass

from kernel_domain.errors import Error, ErrorType
from kernel_domain.result import Result

from application.ports import TicketMutationPort
from domain.ticket import (
    InvalidStatusTransitionError,
    Ticket,
    TicketClosedError,
    TicketStatus,
)


@dataclass(frozen=True)
class ChangeTicketStatusCommand:
    """DTO для изменения статуса тикета."""

    ticket_id: uuid.UUID
    actor_id: uuid.UUID
    status: TicketStatus
    is_admin: bool = False


class ChangeTicketStatusCommandHandler:
    def __init__(self, repository: TicketMutationPort) -> None:
        self._repository = repository

    async def execute(self, command: ChangeTicketStatusCommand) -> Result[Ticket]:
        if not command.is_admin:
            return Result.fail(
                Error(
                    code="FORBIDDEN",
                    description="Доступ только для администраторов!",
                    type=ErrorType.FORBIDDEN,
                )
            )
        try:
            ticket = await self._repository.change_status(
                ticket_id=command.ticket_id,
                actor_id=command.actor_id,
                status=command.status,
            )
        except TicketClosedError:
            return Result.fail(
                Error(
                    code="TICKET_CLOSED",
                    description="Закрытый тикет нельзя изменять",
                    type=ErrorType.CONFLICT,
                )
            )
        except InvalidStatusTransitionError:
            return Result.fail(
                Error(
                    code="INVALID_STATUS_TRANSITION",
                    description="Недопустимый переход статуса тикета",
                    type=ErrorType.CONFLICT,
                )
            )
        if ticket is None:
            return Result.fail(
                Error(
                    code="TICKET_NOT_FOUND",
                    description="Тикет не найден",
                    type=ErrorType.NOT_FOUND,
                )
            )
        return Result.ok(ticket)
