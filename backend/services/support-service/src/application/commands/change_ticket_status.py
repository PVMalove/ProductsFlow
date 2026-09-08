import logging
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

logger = logging.getLogger(__name__)


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
            logger.warning(
                "Смена статуса тикета отклонена: недостаточно прав "
                "actor_id=%s ticket_id=%s",
                command.actor_id,
                command.ticket_id.value,
            )
            return Result[TicketView].fail(SupportErrors.forbidden())
        async with self._uow:
            try:
                ticket = await self._uow.tickets.change_status(
                    ticket_id=command.ticket_id,
                    actor_id=command.actor_id,
                    status=command.status,
                )
            except TicketClosedError:
                logger.warning(
                    "Смена статуса тикета отклонена: тикет закрыт ticket_id=%s",
                    command.ticket_id.value,
                )
                return Result[TicketView].fail(SupportErrors.ticket_closed_conflict())
            except InvalidStatusTransitionError:
                logger.warning(
                    "Смена статуса тикета отклонена: недопустимый переход "
                    "ticket_id=%s status=%s",
                    command.ticket_id.value,
                    command.status,
                )
                return Result[TicketView].fail(
                    SupportErrors.ticket_status_transition_rejected()
                )
            if ticket is None:
                logger.warning(
                    "Смена статуса тикета отклонена: тикет не найден ticket_id=%s",
                    command.ticket_id.value,
                )
                return Result[TicketView].fail(SupportErrors.ticket_not_found())
            await self._uow.commit()
        logger.info(
            "Статус тикета изменён: ticket_id=%s status=%s actor_id=%s",
            command.ticket_id.value,
            command.status,
            command.actor_id,
        )
        return Result[TicketView].ok(TicketView.from_domain(ticket))
