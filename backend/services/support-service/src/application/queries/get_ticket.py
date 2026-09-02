# ruff: noqa: E501
"""Get-ticket query and visibility handler."""

import uuid
from dataclasses import dataclass

from application.ports import TicketQueryPort
from domain.ticket import Ticket


@dataclass(frozen=True)
class GetTicketQuery:
    """DTO для получения тикета по ID."""

    """
    DTO запроса для получения детальной информации о тикете.
    
    Attributes:
        ticket_id (uuid.UUID): Идентификатор запрашиваемого тикета.
        author_id (uuid.UUID): Идентификатор пользователя, выполняющего запрос.
        is_admin (bool): Флаг, указывающий, является ли пользователь администратором.
    """
    ticket_id: uuid.UUID
    author_id: uuid.UUID
    is_admin: bool = False


class GetTicketQueryHandler:
    """
    Business Logic Summary

    Context & Purpose: Чтение детальной информации о тикете.
    Validations: Проверка принадлежности тикета автору запроса или наличия прав администратора.
    Data Sourcing: Данные извлекаются из TicketRepository.
    """

    """
    Business Logic Summary
    
    Context & Purpose: Получает данные тикета с учетом прав доступа.
    Validations: Отсутствуют явные валидации бизнес-логики; применяется проверка прав доступа через ветвление (админ видит любой тикет, клиент — только свой).
    Data Sourcing: Извлекает тикет из TicketQueryPort.
    """

    def __init__(self, repository: TicketQueryPort) -> None:
        self._repository = repository

    async def execute(self, query: GetTicketQuery) -> Ticket | None:
        """
        Выполняет запрос на получение тикета по ID.

        @param query: Объект GetTicketQuery с параметрами поиска и авторизации.
        @return: Найденный Ticket или None, если тикет не существует или недоступен пользователю.
        @raises: Не выбрасывает исключений.
        """
        if query.is_admin:
            return await self._repository.get_by_id(query.ticket_id)
        return await self._repository.get_for_author(query.ticket_id, query.author_id)
