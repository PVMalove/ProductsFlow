from kernel_domain.errors import Error, ErrorType
from kernel_domain.result import Result

from application.password_hasher import PasswordHasher
from application.user_repository import UserRepository
from domain.raw_password import RawPassword
from domain.user import User
from domain.user_id import UserId

_INVALID_CREDENTIALS = Error(
    code="invalid_credentials",
    description="Текущий пароль не совпадает",
    type=ErrorType.UNAUTHORIZED,
)


class ChangePasswordCommand:
    """Смена пароля аутентифицированным пользователем (ADR TD-01 Фаза 1) —
    новый пароль проверяется на стойкость тем же `RawPassword`, что и при
    регистрации; деактивированность агрегата отклоняет сам `User.change_password`."""

    def __init__(
        self, user_repository: UserRepository, password_hasher: PasswordHasher
    ) -> None:
        self._user_repository = user_repository
        self._password_hasher = password_hasher

    def execute(
        self, user_id: UserId, old_password: str, new_password: str
    ) -> Result[User]:
        user = self._user_repository.get_by_id(user_id)
        if user is None or not self._password_hasher.verify(
            old_password, user.password_hash
        ):
            return Result.fail(_INVALID_CREDENTIALS)

        raw_password_result = RawPassword.create(new_password)
        if raw_password_result.is_err:
            return Result.fail(raw_password_result.error)

        new_password_hash = self._password_hasher.hash(raw_password_result.value.value)
        result = user.change_password(new_password_hash)
        if result.is_err:
            return Result.fail(result.error)

        return Result.ok(user)
