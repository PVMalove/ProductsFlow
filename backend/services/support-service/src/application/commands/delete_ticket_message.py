import logging
import uuid
from dataclasses import dataclass

from kernel_domain.result import Result

from domain.entities.ticket import (
    TicketClosedError,
    TicketMessageAlreadyDeletedError,
    TicketMessageImmutableError,
    TicketMessageNotFoundError,
)
from domain.errors import SupportErrors
from domain.unit_of_work import SupportUnitOfWork
from domain.value_objects.ticket_id import TicketId

logger = logging.getLogger(__name__)


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
                logger.warning(
                    "Удаление сообщения отклонено: сообщение не найдено "
                    "ticket_id=%s message_id=%s",
                    command.ticket_id.value,
                    command.message_id,
                )
                return Result[None].fail(SupportErrors.ticket_message_not_found())
            except (
                TicketClosedError,
                TicketMessageImmutableError,
                TicketMessageAlreadyDeletedError,
            ):
                logger.warning(
                    "Удаление сообщения отклонено: сообщение неизменяемо "
                    "ticket_id=%s message_id=%s",
                    command.ticket_id.value,
                    command.message_id,
                )
                return Result[None].fail(
                    SupportErrors.ticket_message_immutable("удалить")
                )
            if ticket is None:
                logger.warning(
                    "Удаление сообщения отклонено: тикет не найден ticket_id=%s",
                    command.ticket_id.value,
                )
                return Result[None].fail(SupportErrors.ticket_not_found())
            await self._uow.commit()
        logger.info(
            "Сообщение удалено: ticket_id=%s message_id=%s actor_id=%s",
            command.ticket_id.value,
            command.message_id,
            command.actor_id,
        )
        return Result[None].ok(None)
