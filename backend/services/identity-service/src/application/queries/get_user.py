"""Get-user query and read-only handler."""

from dataclasses import dataclass

from kernel_domain.errors import Error, ErrorType
from kernel_domain.result import Result

from application.ports import UserQueryPort, UserReadModel
from domain.user_id import UserId


@dataclass(frozen=True)
class GetUserQuery:
    user_id: UserId


class GetUserQueryHandler:
    def __init__(self, users: UserQueryPort) -> None:
        self._users = users

    def handle(self, query: GetUserQuery) -> Result[UserReadModel]:
        read_model = self._users.get_by_id(query.user_id)
        if read_model is None:
            return Result.fail(
                Error(
                    code="user_not_found",
                    description="Пользователь не найден",
                    type=ErrorType.NOT_FOUND,
                )
            )
        return Result.ok(read_model)
