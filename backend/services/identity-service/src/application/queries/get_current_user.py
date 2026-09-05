"""Query и handler get-current-user (ADR 0005).

`/users/me` не доверяет claims JWT как источнику своего ответа: security-
зависимость только аутентифицирует и строит transport-neutral `Actor`, а
этот handler перечитывает актуальное состояние вызывающего и возвращает
framework-independent `UserView`."""

from dataclasses import dataclass

from kernel_domain.result import Result

from application.ports import UserQueryPort
from contracts.user import UserView
from domain.errors import IdentityErrors
from domain.value_objects.user_id import UserId


@dataclass(frozen=True)
class GetCurrentUserQuery:
    user_id: UserId


class GetCurrentUserHandler:
    def __init__(self, users: UserQueryPort) -> None:
        self._users = users

    async def execute(self, query: GetCurrentUserQuery) -> Result[UserView]:
        user = await self._users.get_by_id(query.user_id)
        if user is None:
            return Result[UserView].fail(IdentityErrors.user_not_found())
        return Result[UserView].ok(UserView.from_user(user))
