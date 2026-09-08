import logging
import uuid
from dataclasses import dataclass

from kernel_domain.result import Result

from contracts.ticket import TicketView
from domain.entities.ticket import (
    TicketClosedError,
    TicketMessageAlreadyDeletedError,
    TicketMessageImmutableError,
    TicketMessageInvalidBodyError,
    TicketMessageNotFoundError,
)
from domain.errors import SupportErrors
from domain.unit_of_work import SupportUnitOfWork
from domain.value_objects.ticket_id import TicketId

logger = logging.getLogger(__name__)


@dataclass(frozen=True)
class EditTicketMessageCommand:
    ticket_id: TicketId
    message_id: uuid.UUID
    actor_id: uuid.UUID
    body: str
    is_admin: bool = False


class EditTicketMessageCommandHandler:
    def __init__(self, uow: SupportUnitOfWork) -> None:
        self._uow = uow

    async def execute(self, command: EditTicketMessageCommand) -> Result[TicketView]:
        async with self._uow:
            try:
                ticket = await self._uow.tickets.edit_message(
                    ticket_id=command.ticket_id,
                    message_id=command.message_id,
                    actor_id=command.actor_id,
                    body=command.body,
                    is_admin=command.is_admin,
                )
            except TicketMessageNotFoundError:
                logger.warning(
                    "Редактирование сообщения отклонено: сообщение не найдено "
                    "ticket_id=%s message_id=%s",
                    command.ticket_id.value,
                    command.message_id,
                )
                return Result[TicketView].fail(SupportErrors.ticket_message_not_found())
            except (
                TicketClosedError,
                TicketMessageImmutableError,
                TicketMessageAlreadyDeletedError,
            ):
                logger.warning(
                    "Редактирование сообщения отклонено: сообщение неизменяемо "
                    "ticket_id=%s message_id=%s",
                    command.ticket_id.value,
                    command.message_id,
                )
                return Result[TicketView].fail(
                    SupportErrors.ticket_message_immutable("изменить")
                )
            except TicketMessageInvalidBodyError:
                return Result[TicketView].fail(SupportErrors.invalid_body())
            if ticket is None:
                logger.warning(
                    "Редактирование сообщения отклонено: тикет не найден ticket_id=%s",
                    command.ticket_id.value,
                )
                return Result[TicketView].fail(SupportErrors.ticket_not_found())
            await self._uow.commit()
        logger.info(
            "Сообщение отредактировано: ticket_id=%s message_id=%s actor_id=%s",
            command.ticket_id.value,
            command.message_id,
            command.actor_id,
        )
        return Result[TicketView].ok(TicketView.from_domain(ticket))
