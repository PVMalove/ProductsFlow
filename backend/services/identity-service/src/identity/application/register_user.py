from kernel_domain.errors import Error, ErrorType
from kernel_domain.result import Result

from identity.application.password_hasher import PasswordHasher
from identity.application.user_repository import UserRepository
from identity.domain.email import Email
from identity.domain.user import User


class RegisterUserCommand:
    """Регистрация пользователя (ADR TD-01 Фаза 1) — уникальность email
    проверяется здесь, до конструирования агрегата: `User` не имеет доступа
    к репозиторию и не может проверить это сам."""

    def __init__(
        self, user_repository: UserRepository, password_hasher: PasswordHasher
    ) -> None:
        self._user_repository = user_repository
        self._password_hasher = password_hasher

    def execute(self, email: str, password: str) -> Result[User]:
        email_vo = Email(email)
        if self._user_repository.exists_by_email(email_vo):
            return Result.fail(
                Error(
                    code="email_already_registered",
                    description=f"Email {email!r} уже зарегистрирован",
                    type=ErrorType.CONFLICT,
                )
            )

        password_hash = self._password_hasher.hash(password)
        result = User.register(email_vo, password_hash)
        if result.is_err:
            return result

        self._user_repository.add(result.value)
        return result
