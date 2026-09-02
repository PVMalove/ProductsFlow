# ruff: noqa: E501
import uuid
from dataclasses import dataclass

from application.errors import TicketNotFoundError
from application.ports import TicketMutationPort
from domain.ticket import Ticket, TicketStatus


@dataclass(frozen=True)
class ChangeTicketStatusCommand:
    """DTO для изменения статуса тикета."""

    """
    DTO команды для изменения статуса тикета поддержки.
    
    Attributes:
        ticket_id (uuid.UUID): Идентификатор тикета.
        actor_id (uuid.UUID): Идентификатор пользователя, инициировавшего изменение.
        status (TicketStatus): Новый статус, который должен быть установлен для тикета.
    """
    ticket_id: uuid.UUID
    actor_id: uuid.UUID
    status: TicketStatus


class ChangeTicketStatusCommandHandler:
    """
    Business Logic Summary

    Context & Purpose: Перевод тикета в новый статус (например, In Progress, Closed).
    Validations: Доступно только администраторам. Валидация разрешенных переходов статуса.
    Side Effects: Обновляется статус агрегата Ticket в репозитории.
    """

    """
    Business Logic Summary
    
    Context & Purpose: Изменяет текущий статус существующего тикета поддержки.
    Validations: Проверяет наличие тикета по указанному ID.
    Side Effects: Обновляет статус тикета в репозитории через TicketMutationPort.
    """

    def __init__(self, repository: TicketMutationPort) -> None:
        self._repository = repository

    async def execute(self, command: ChangeTicketStatusCommand) -> Ticket:
        """
        Выполняет изменение статуса тикета.

        @param command: Объект ChangeTicketStatusCommand с данными для изменения статуса.
        @return: Ticket — обновленная сущность тикета.
        @raises: TicketNotFoundError, если тикет с указанным ID не найден.
        """
        ticket = await self._repository.change_status(
            ticket_id=command.ticket_id,
            actor_id=command.actor_id,
            status=command.status,
        )
        if ticket is None:
            raise TicketNotFoundError
        return ticket
