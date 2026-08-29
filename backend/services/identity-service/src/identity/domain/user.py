from kernel_domain.entity import Entity
from kernel_domain.errors import Error, ErrorType
from kernel_domain.result import Result

from identity.domain.email import Email
from identity.domain.events import UserRegistered
from identity.domain.role import Role
from identity.domain.user_id import UserId

_MIN_PASSWORD_LENGTH = 8


class User(Entity[UserId]):
    """Агрегат учётной записи (ADR TD-01 Фаза 1). Не видит plaintext-пароль
    и не занимается хешированием — `password_hash` приходит уже вычисленным
    от вызывающего слоя (`PasswordHasher`-порт), домен только проверяет его
    на соответствие правилам стойкости пароля."""

    def __init__(
        self,
        id: UserId,
        *,
        email: Email,
        password_hash: str,
        role: Role,
        is_active: bool,
    ) -> None:
        super().__init__(id)
        self.email = email
        self.password_hash = password_hash
        self.role = role
        self.is_active = is_active

    @classmethod
    def register(cls, email: Email, password_hash: str) -> Result["User"]:
        error = _validate_password(password_hash)
        if error is not None:
            return Result.fail(error)

        user = cls(
            UserId.generate(),
            email=email,
            password_hash=password_hash,
            role=Role.USER,
            is_active=True,
        )
        user.add_domain_event(UserRegistered(user_id=user.id, email=email))
        return Result.ok(user)


def _validate_password(value: str) -> Error | None:
    if len(value) < _MIN_PASSWORD_LENGTH:
        return Error(
            code="password_too_short",
            description="Пароль должен содержать минимум 8 символов",
            type=ErrorType.VALIDATION,
        )
    if not any(ch.islower() for ch in value):
        return Error(
            code="password_missing_lowercase",
            description="Пароль должен содержать строчную букву",
            type=ErrorType.VALIDATION,
        )
    if not any(ch.isdigit() for ch in value):
        return Error(
            code="password_missing_digit",
            description="Пароль должен содержать цифру",
            type=ErrorType.VALIDATION,
        )
    return None
