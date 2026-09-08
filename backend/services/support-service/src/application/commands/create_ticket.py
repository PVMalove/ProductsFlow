# ruff: noqa: E501
"""Команда и handler create-ticket."""

import logging
import uuid
from dataclasses import dataclass

from kernel_domain.result import Result

from contracts.ticket import TicketDetailView
from domain.entities.ticket import Ticket
from domain.unit_of_work import SupportUnitOfWork

logger = logging.getLogger(__name__)


@dataclass(frozen=True)
class CreateTicketCommand:
    """DTO для создания нового тикета."""

    author_id: uuid.UUID
    subject: str
    first_message: str


class CreateTicketCommandHandler:
    def __init__(self, uow: SupportUnitOfWork) -> None:
        self._uow = uow

    async def execute(self, command: CreateTicketCommand) -> Result[TicketDetailView]:
        result = Ticket.create(
            author_id=command.author_id,
            subject=command.subject,
            first_message=command.first_message,
        )
        if result.is_err:
            logger.warning(
                "Создание тикета отклонено: author_id=%s code=%s",
                command.author_id,
                result.error.code,
            )
            return Result[TicketDetailView].fail(result.error)

        async with self._uow:
            created = await self._uow.tickets.create(result.value)
            await self._uow.commit()
        logger.info(
            "Тикет создан: ticket_id=%s author_id=%s",
            created.id.value,
            command.author_id,
        )
        return Result[TicketDetailView].ok(
            TicketDetailView.from_domain(created, created.messages)
        )
