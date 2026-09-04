# ruff: noqa: E501
import uuid
from dataclasses import dataclass

from kernel_domain.errors import Error, ErrorType
from kernel_domain.result import Result

from domain.entities.ticket import (
    TicketClosedError,
    TicketMessageAlreadyDeletedError,
    TicketMessageImmutableError,
    TicketMessageNotFoundError,
)
from domain.unit_of_work import SupportUnitOfWork
from domain.value_objects.ticket_id import TicketId


@dataclass(frozen=True)
class DeleteTicketMessageCommand:
    ticket_id: TicketId
    message_id: uuid.UUID
    actor_id: uuid.UUID
    is_admin: bool = False


class DeleteTicketMessageCommandHandler:
    def __init__(self, uow: SupportUnitOfWork) -> None:
        self._uow = uow

    async def execute(self, command: DeleteTicketMessageCommand) -> Result[None]:
        async with self._uow:
            try:
                ticket = await self._uow.tickets.delete_message(
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
            await self._uow.commit()
        return Result[None].ok(None)
