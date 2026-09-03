# ruff: noqa: E501
import uuid
from dataclasses import dataclass

from kernel_domain.errors import Error, ErrorType
from kernel_domain.result import Result

from application.ports import TicketMutationPort
from domain.ticket import (
    Ticket,
    TicketClosedError,
    TicketMessageAlreadyDeletedError,
    TicketMessageImmutableError,
    TicketMessageNotFoundError,
)


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

    async def execute(self, command: EditTicketMessageCommand) -> Result[Ticket]:
        try:
            ticket = await self._repository.edit_message(
                ticket_id=command.ticket_id,
                message_id=command.message_id,
                actor_id=command.actor_id,
                body=command.body,
                is_admin=command.is_admin,
            )
        except TicketMessageNotFoundError:
            return Result[Ticket].fail(
                Error(
                    code="TICKET_MESSAGE_NOT_FOUND",
                    description="Тикет не найден",
                    type=ErrorType.NOT_FOUND,
                )
            )
        except (
            TicketClosedError,
            TicketMessageImmutableError,
            TicketMessageAlreadyDeletedError,
        ):
            return Result[Ticket].fail(
                Error(
                    code="TICKET_MESSAGE_IMMUTABLE",
                    description="Сообщение нельзя изменить",
                    type=ErrorType.CONFLICT,
                )
            )
        if ticket is None:
            return Result[Ticket].fail(
                Error(
                    code="TICKET_NOT_FOUND",
                    description="Тикет не найден",
                    type=ErrorType.NOT_FOUND,
                )
            )
        return Result[Ticket].ok(ticket)
