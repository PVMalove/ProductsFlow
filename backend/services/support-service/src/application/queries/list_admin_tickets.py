# ruff: noqa: E501
"""Query и handler list-all-tickets."""

from dataclasses import dataclass

from kernel_domain.errors import Error, ErrorType
from kernel_domain.result import Result

from application.ports import TicketQueryPort
from domain.repositories import Cursor, TicketPage


@dataclass(frozen=True)
class ListAdminTicketsQuery:
    """DTO для получения всех тикетов (админ)."""

    limit: int
    is_admin: bool = False
    after: Cursor | None = None
    before: Cursor | None = None


class ListAdminTicketsQueryHandler:
    """
    Business Logic Summary

    Context & Purpose: Получение полного списка тикетов в системе для администраторов.
    Validations: Владеет решением об авторизации сама (ADR 0006) — не контроллер.
    Data Sourcing: TicketRepository, с поддержкой курсорной пагинации.
    """

    def __init__(self, repository: TicketQueryPort) -> None:
        self._repository = repository

    async def execute(self, query: ListAdminTicketsQuery) -> Result[TicketPage]:
        if not query.is_admin:
            return Result[TicketPage].fail(
                Error(
                    code="FORBIDDEN",
                    description="Доступ только для администраторов!",
                    type=ErrorType.FORBIDDEN,
                )
            )
        page = await self._repository.list_all(
            limit=query.limit,
            after=query.after,
            before=query.before,
        )
        return Result[TicketPage].ok(page)
