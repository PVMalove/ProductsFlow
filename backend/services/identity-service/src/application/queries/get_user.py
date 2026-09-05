"""Query и read-only handler get-user."""

from dataclasses import dataclass

from kernel_domain.result import Result

from application.ports import UserQueryPort, UserReadModel
from domain.errors import IdentityErrors
from domain.value_objects.user_id import UserId


@dataclass(frozen=True)
class GetUserQuery:
    """DTO запроса для получения данных пользователя.

    Attributes:
        user_id (UserId): Уникальный идентификатор пользователя.
    """

    user_id: UserId


class GetUserQueryHandler:
    """
    Business Logic Summary

    Context & Purpose: Получение данных профиля пользователя по его ID.
    Validations: Проверяет существование пользователя; авторизация (свои
    данные или админ) обеспечивается на границе API.
    Data Sourcing: Данные извлекаются через query-порт по ID.
    """

    def __init__(self, users: UserQueryPort) -> None:
        self._users = users

    async def execute(self, query: GetUserQuery) -> Result[UserReadModel]:
        """
        Выполняет запрос на получение пользователя.

        @param query: Объект GetUserQuery, содержащий идентификатор пользователя.
        @return: Result[UserReadModel] или Error при отсутствии.
        @raises: Не выбрасывает исключений (использует паттерн Result).
        """
        read_model = await self._users.get_by_id(query.user_id)
        if read_model is None:
            return Result[UserReadModel].fail(IdentityErrors.user_not_found())
        return Result[UserReadModel].ok(read_model)
