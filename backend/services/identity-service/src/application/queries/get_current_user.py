"""Get-current-user query and handler (ADR 0033).

`/users/me` does not trust JWT claims as the source of its response: the
security dependency only authenticates and builds the transport-neutral
`Actor`, while this handler reloads the caller's current state and returns
the framework-independent `UserView`."""

from dataclasses import dataclass

from kernel_domain.errors import Error, ErrorType
from kernel_domain.result import Result

from application.ports import UserQueryPort
from contracts.user import UserView
from domain.user_id import UserId


@dataclass(frozen=True)
class GetCurrentUserQuery:
    user_id: UserId


class GetCurrentUserHandler:
    def __init__(self, users: UserQueryPort) -> None:
        self._users = users

    async def execute(self, query: GetCurrentUserQuery) -> Result[UserView]:
        user = await self._users.get_by_id(query.user_id)
        if user is None:
            return Result.fail(
                Error(
                    code="user_not_found",
                    description="Пользователь не найден",
                    type=ErrorType.NOT_FOUND,
                )
            )
        return Result.ok(UserView.from_user(user))
