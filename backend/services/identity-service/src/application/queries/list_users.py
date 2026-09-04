"""Query и handler list-users."""

from dataclasses import dataclass

from kernel_platform.pagination import Cursor

from application.ports import UserListQueryPort, UserPage


@dataclass(frozen=True)
class ListUsersQuery:
    """DTO для курсорно-пагинированного списка пользователей администратора."""

    limit: int
    after: Cursor | None = None
    before: Cursor | None = None


class ListUsersQueryHandler:
    """Читает пользователей через query-side порт."""

    def __init__(self, users: UserListQueryPort) -> None:
        self._users = users

    async def execute(self, query: ListUsersQuery) -> UserPage:
        return await self._users.list(
            limit=query.limit, after=query.after, before=query.before
        )
