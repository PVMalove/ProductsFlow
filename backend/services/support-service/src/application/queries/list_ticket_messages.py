# ruff: noqa: E501
"""List-ticket-messages query and handler."""

import uuid
from dataclasses import dataclass

from application.ports import TicketQueryPort
from domain.repositories import Cursor, MessagePage


@dataclass(frozen=True)
class ListTicketMessagesQuery:
    """DTO для получения сообщений тикета."""

    ticket_id: uuid.UUID
    limit: int
    after: Cursor | None = None
    before: Cursor | None = None


class ListTicketMessagesQueryHandler:
    """
    Business Logic Summary

    Context & Purpose: Получение списка сообщений для конкретного тикета.
    Validations: Проверка доступа делегируется GetTicketQueryHandler.
    Data Sourcing: TicketRepository извлекает сообщения с пагинацией.
    """

    def __init__(self, repository: TicketQueryPort) -> None:
        self._repository = repository

    async def execute(self, query: ListTicketMessagesQuery) -> MessagePage:
        return await self._repository.list_messages(
            ticket_id=query.ticket_id,
            limit=query.limit,
            after=query.after,
            before=query.before,
        )
