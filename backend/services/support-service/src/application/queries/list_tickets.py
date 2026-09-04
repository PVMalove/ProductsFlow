# ruff: noqa: E501
"""Query и handler list-owned-tickets."""

import uuid
from dataclasses import dataclass

from application.ports import TicketQueryPort
from domain.repositories import Cursor, TicketPage


@dataclass(frozen=True)
class ListTicketsQuery:
    """DTO для получения тикетов пользователя."""

    author_id: uuid.UUID
    limit: int
    after: Cursor | None = None
    before: Cursor | None = None


class ListTicketsQueryHandler:
    """
    Business Logic Summary

    Context & Purpose: Получение списка тикетов, созданных конкретным пользователем.
    Validations: Данные фильтруются строго по author_id из токена авторизации.
    Data Sourcing: TicketRepository, выборка тикетов пользователя с пагинацией.
    """

    def __init__(self, repository: TicketQueryPort) -> None:
        self._repository = repository

    async def execute(self, query: ListTicketsQuery) -> TicketPage:
        return await self._repository.list_for_author(
            author_id=query.author_id,
            limit=query.limit,
            after=query.after,
            before=query.before,
        )
