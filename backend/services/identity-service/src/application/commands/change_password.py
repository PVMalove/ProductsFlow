"""Change-password command and handler."""

from dataclasses import dataclass

from kernel_domain.errors import Error, ErrorType
from kernel_domain.result import Result

from application.ports import PasswordHasher
from domain.raw_password import RawPassword
from domain.repositories import UserRepository
from domain.user import User
from domain.user_id import UserId


@dataclass(frozen=True)
class ChangePasswordCommand:
    """DTO для изменения пароля пользователя."""

    user_id: UserId
    old_password: str
    new_password: str


class ChangePasswordCommandHandler:
    """
    Business Logic Summary

    Context & Purpose: Смена пароля текущего пользователя.
    Validations: Сравнение старого пароля, проверка сложности нового пароля.
    Side Effects: Пароль в репозитории обновляется (хешируется).
    """

    def __init__(self, users: UserRepository, password_hasher: PasswordHasher) -> None:
        self._users = users
        self._password_hasher = password_hasher

    async def execute(self, command: ChangePasswordCommand) -> Result[User]:
        user = await self._users.get_by_id(command.user_id)
        if user is None or not self._password_hasher.verify(
            command.old_password, user.password_hash
        ):
            return Result[User].fail(
                Error(
                    code="invalid_credentials",
                    description="Текущий пароль не совпадает",
                    type=ErrorType.UNAUTHORIZED,
                )
            )
        password = RawPassword.create(command.new_password)
        if password.is_err:
            return Result[User].fail(password.error)
        result = user.change_password(self._password_hasher.hash(password.value.value))
        if result.is_err:
            return Result[User].fail(result.error)
        await self._users.save(user)
        return Result[User].ok(user)
