from kernel_domain.errors import Error, ErrorType
from kernel_domain.result import Result

from application.password_hasher import PasswordHasher
from domain.email import Email
from domain.raw_password import RawPassword
from domain.repositories import UserRepository
from domain.user import User


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

        raw_password_result = RawPassword.create(password)
        if raw_password_result.is_err:
            return Result.fail(raw_password_result.error)

        password_hash = self._password_hasher.hash(raw_password_result.value.value)
        result = User.register(email_vo, password_hash)
        if result.is_err:
            return result

        self._user_repository.add(result.value)
        return result
