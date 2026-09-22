"""Query и handler для глобального audit-фида."""

from dataclasses import dataclass

from kernel_domain.result import Result
from kernel_platform.pagination import DEFAULT_PAGE_LIMIT

from application.ports import (
    UserAuditPage,
    UserAuditQueryPort,
)


@dataclass(frozen=True)
class GetGlobalAuditQuery:
    """Читает глобальный админский audit-фид с пагинацией."""

    page_index: int = 1
    page_size: int = DEFAULT_PAGE_LIMIT


class GetGlobalAuditQueryHandler:
    """Обрабатывает пагинированный запрос глобального audit-фида."""

    def __init__(self, audit: UserAuditQueryPort) -> None:
        self._audit = audit

    async def execute(self, query: GetGlobalAuditQuery) -> Result[UserAuditPage]:
        page = await self._audit.list_all(
            page_index=query.page_index, page_size=query.page_size
        )
        return Result[UserAuditPage].ok(page)
