# ruff: noqa: E501
import uuid
from dataclasses import dataclass

from kernel_domain.errors import Error, ErrorType
from kernel_domain.result import Result

from application.ports import TicketMutationPort
from domain.ticket import (
    TicketClosedError,
    TicketMessageAlreadyDeletedError,
    TicketMessageImmutableError,
    TicketMessageNotFoundError,
)


@dataclass(frozen=True)
class DeleteTicketMessageCommand:
    ticket_id: uuid.UUID
    message_id: uuid.UUID
    actor_id: uuid.UUID
    is_admin: bool = False


class DeleteTicketMessageCommandHandler:
    def __init__(self, repository: TicketMutationPort) -> None:
        self._repository = repository

    async def execute(self, command: DeleteTicketMessageCommand) -> Result[None]:
        try:
            ticket = await self._repository.delete_message(
                ticket_id=command.ticket_id,
                message_id=command.message_id,
                actor_id=command.actor_id,
                is_admin=command.is_admin,
            )
        except TicketMessageNotFoundError:
            return Result[None].fail(
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
            return Result[None].fail(
                Error(
                    code="TICKET_MESSAGE_IMMUTABLE",
                    description="Сообщение нельзя удалить",
                    type=ErrorType.CONFLICT,
                )
            )
        if ticket is None:
            return Result[None].fail(
                Error(
                    code="TICKET_NOT_FOUND",
                    description="Тикет не найден",
                    type=ErrorType.NOT_FOUND,
                )
            )
        return Result[None].ok(None)
