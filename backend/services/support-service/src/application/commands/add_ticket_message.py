# ruff: noqa: E501
import uuid
from dataclasses import dataclass

from kernel_domain.errors import Error, ErrorType
from kernel_domain.result import Result

from application.ports import TicketMutationPort
from contracts.ticket import TicketView
from domain.ticket import TicketClosedError


@dataclass(frozen=True)
class AddTicketMessageCommand:
    """DTO для добавления сообщения в тикет."""

    ticket_id: uuid.UUID
    actor_id: uuid.UUID
    body: str
    is_admin: bool = False


class AddTicketMessageCommandHandler:
    def __init__(self, repository: TicketMutationPort) -> None:
        self._repository = repository

    async def execute(self, command: AddTicketMessageCommand) -> Result[TicketView]:
        try:
            ticket = await self._repository.add_message(
                ticket_id=command.ticket_id,
                actor_id=command.actor_id,
                body=command.body,
                is_admin=command.is_admin,
            )
        except TicketClosedError:
            return Result[TicketView].fail(
                Error(
                    code="TICKET_CLOSED",
                    description="Закрытый тикет нельзя изменять",
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
        return Result[TicketView].ok(TicketView.from_domain(ticket))
