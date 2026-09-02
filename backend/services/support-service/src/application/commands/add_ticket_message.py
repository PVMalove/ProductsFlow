# ruff: noqa: E501
import uuid
from dataclasses import dataclass

from application.errors import TicketNotFoundError
from application.ports import TicketMutationPort
from domain.ticket import Ticket


@dataclass(frozen=True)
class AddTicketMessageCommand:
    """DTO для добавления сообщения в тикет."""

    """
    DTO команды для добавления сообщения в тикет поддержки.
    
    Attributes:
        ticket_id (uuid.UUID): Идентификатор тикета, к которому добавляется сообщение.
        actor_id (uuid.UUID): Идентификатор пользователя (клиента или администратора), отправляющего сообщение.
        body (str): Текст сообщения.
        is_admin (bool): Флаг, указывающий, является ли отправитель администратором.
    """
    ticket_id: uuid.UUID
    actor_id: uuid.UUID
    body: str
    is_admin: bool = False


class AddTicketMessageCommandHandler:
    """
    Business Logic Summary

    Context & Purpose: Добавление нового комментария/ответа в существующий тикет.
    Validations: Проверка прав (создатель тикета или админ), проверка статуса тикета (не закрыт).
    Side Effects: Новое сообщение добавляется в агрегат Ticket и сохраняется.
    """

    """
    Business Logic Summary
    
    Context & Purpose: Добавляет новое сообщение в существующий тикет поддержки.
    Validations: Проверяет, что тикет существует (бросает исключение, если не найден).
    Side Effects: Мутирует состояние тикета, добавляя новое сообщение через TicketMutationPort.
    """

    def __init__(self, repository: TicketMutationPort) -> None:
        self._repository = repository

    async def execute(self, command: AddTicketMessageCommand) -> Ticket:
        """
        Выполняет добавление сообщения в тикет.

        @param command: Объект AddTicketMessageCommand с данными сообщения.
        @return: Ticket — обновленная сущность тикета.
        @raises: TicketNotFoundError, если тикет с указанным ID не найден.
        """
        ticket = await self._repository.add_message(
            ticket_id=command.ticket_id,
            actor_id=command.actor_id,
            body=command.body,
            is_admin=command.is_admin,
        )
        if ticket is None:
            raise TicketNotFoundError
        return ticket
