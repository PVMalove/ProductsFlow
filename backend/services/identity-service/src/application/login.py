from kernel_domain.errors import Error, ErrorType
from kernel_domain.result import Result

from application.password_hasher import PasswordHasher
from domain.email import Email
from domain.repositories import UserRepository
from domain.user import User

_INVALID_CREDENTIALS = Error(
    code="invalid_credentials",
    description="Неверный email или пароль",
    type=ErrorType.UNAUTHORIZED,
)


class LoginCommand:
    """Аутентификация по email/паролю (ADR TD-01 Фаза 1) — несуществующий
    email и неверный пароль отдают одну и ту же `UNAUTHORIZED`-ошибку, чтобы
    не раскрывать вызывающему факт существования аккаунта."""

    def __init__(
        self, user_repository: UserRepository, password_hasher: PasswordHasher
    ) -> None:
        self._user_repository = user_repository
        self._password_hasher = password_hasher

    def execute(self, email: str, password: str) -> Result[User]:
        email_vo = Email(email)
        user = self._user_repository.get_by_email(email_vo)
        if user is None or not self._password_hasher.verify(
            password, user.password_hash
        ):
            return Result.fail(_INVALID_CREDENTIALS)

        if not user.is_active:
            return Result.fail(
                Error(
                    code="user_deactivated",
                    description="Пользователь деактивирован",
                    type=ErrorType.FORBIDDEN,
                )
            )

        return Result.ok(user)
