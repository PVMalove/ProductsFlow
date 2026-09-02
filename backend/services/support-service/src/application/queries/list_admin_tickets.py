# ruff: noqa: E501
"""List-all-tickets query and handler."""

from dataclasses import dataclass

from application.ports import TicketQueryPort
from domain.repositories import Cursor, TicketPage


@dataclass(frozen=True)
class ListAdminTicketsQuery:
    """DTO для получения всех тикетов (админ)."""

    limit: int
    after: Cursor | None = None
    before: Cursor | None = None


class ListAdminTicketsQueryHandler:
    """
    Business Logic Summary

    Context & Purpose: Получение полного списка тикетов в системе для администраторов.
    Validations: Проверяется наличие роли администратора (на уровне контроллера/middleware).
    Data Sourcing: TicketRepository, с поддержкой курсорной пагинации.
    """

    def __init__(self, repository: TicketQueryPort) -> None:
        self._repository = repository

    async def execute(self, query: ListAdminTicketsQuery) -> TicketPage:
        return await self._repository.list_all(
            limit=query.limit,
            after=query.after,
            before=query.before,
        )
