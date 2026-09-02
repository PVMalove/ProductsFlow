"""User-audit query and handler."""

from dataclasses import dataclass

from kernel_platform.pagination import DEFAULT_PAGE_LIMIT

from application.ports import UserAuditEntry, UserAuditPage, UserAuditQueryPort
from domain.user_id import UserId


@dataclass(frozen=True)
class GetUserAuditQuery:
    """Read global audit data or one user's complete audit history.

    ``user_id=None`` selects the global administrator feed. Supplying a user
    id selects either the caller's own history or an administrator's target
    history; authorization is enforced by the API boundary.
    """

    user_id: UserId | None = None
    page_index: int = 1
    page_size: int = DEFAULT_PAGE_LIMIT


class GetUserAuditQueryHandler:
    """Select the paginated global or unpaginated personal audit mode."""

    def __init__(self, audit: UserAuditQueryPort) -> None:
        self._audit = audit

    async def execute(
        self, query: GetUserAuditQuery
    ) -> UserAuditPage | list[UserAuditEntry]:
        if query.user_id is not None:
            return await self._audit.get_by_user(query.user_id)
        return await self._audit.list_all(
            page_index=query.page_index, page_size=query.page_size
        )
