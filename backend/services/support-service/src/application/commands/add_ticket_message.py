import logging
import uuid
from dataclasses import dataclass

from kernel_domain.result import Result

from contracts.ticket import TicketView
from domain.entities.ticket import TicketClosedError, TicketMessageInvalidBodyError
from domain.errors import SupportErrors
from domain.unit_of_work import SupportUnitOfWork
from domain.value_objects.ticket_id import TicketId

logger = logging.getLogger(__name__)


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
                logger.warning(
                    "Добавление сообщения отклонено: тикет закрыт ticket_id=%s",
                    command.ticket_id.value,
                )
                return Result[TicketView].fail(SupportErrors.ticket_closed_conflict())
            except TicketMessageInvalidBodyError:
                return Result[TicketView].fail(SupportErrors.invalid_body())
            if ticket is None:
                logger.warning(
                    "Добавление сообщения отклонено: тикет не найден ticket_id=%s",
                    command.ticket_id.value,
                )
                return Result[TicketView].fail(SupportErrors.ticket_not_found())
            await self._uow.commit()
        logger.info(
            "Сообщение добавлено в тикет: ticket_id=%s actor_id=%s",
            command.ticket_id.value,
            command.actor_id,
        )
        return Result[TicketView].ok(TicketView.from_domain(ticket))
