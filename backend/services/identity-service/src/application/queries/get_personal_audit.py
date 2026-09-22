"""Query и handler для личного audit-фида пользователя."""

from dataclasses import dataclass

from kernel_domain.result import Result

from application.ports import (
    UserAuditEntry,
    UserAuditQueryPort,
    UserQueryPort,
)
from domain.errors import IdentityErrors
from domain.value_objects.user_id import UserId


@dataclass(frozen=True)
class GetPersonalAuditQuery:
    """Читает непагинированную audit-историю конкретного пользователя."""

    user_id: UserId


class GetPersonalAuditQueryHandler:
    """Обрабатывает запрос личного audit-фида."""

    def __init__(self, audit: UserAuditQueryPort, users: UserQueryPort) -> None:
        self._audit = audit
        self._users = users

    async def execute(
        self, query: GetPersonalAuditQuery
    ) -> Result[list[UserAuditEntry]]:
        if await self._users.get_by_id(query.user_id) is None:
            return Result[list[UserAuditEntry]].fail(IdentityErrors.user_not_found())
        entries = await self._audit.get_by_user(query.user_id)
        return Result[list[UserAuditEntry]].ok(entries)
