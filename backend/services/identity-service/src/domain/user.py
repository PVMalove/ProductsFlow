from kernel_domain.entity import Entity
from kernel_domain.errors import Error, ErrorType
from kernel_domain.result import Result

from domain.email import Email
from domain.events import (
    Activated,
    Deactivated,
    PasswordChanged,
    UserRegistered,
)
from domain.role import Role
from domain.user_id import UserId


class User(Entity[UserId]):
    """Агрегат учётной записи (ADR TD-01 Фаза 1). Не видит plaintext-пароль
    и не занимается хешированием — `password_hash` приходит уже вычисленным
    от вызывающего слоя (`PasswordHasher`-порт). Стойкость исходного пароля
    проверяется раньше, доменным VO `RawPassword`, не здесь — `password_hash`
    как таковой не несёт признаков, по которым эту стойкость можно было бы
    осмысленно перепроверить."""

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
        user = cls(
            UserId.generate(),
            email=email,
            password_hash=password_hash,
            role=Role.USER,
            is_active=True,
        )
        user.add_domain_event(UserRegistered(user_id=user.id, email=email))
        return Result.ok(user)

    def change_password(self, new_password_hash: str) -> Result[None]:
        if not self.is_active:
            return Result.fail(
                Error(
                    code="user_deactivated",
                    description="Деактивированный пользователь не может сменить пароль",
                    type=ErrorType.FORBIDDEN,
                )
            )

        self.password_hash = new_password_hash
        self.add_domain_event(PasswordChanged(user_id=self.id))
        return Result.ok(None)

    def deactivate(self) -> Result[None]:
        if not self.is_active:
            return Result.fail(
                Error(
                    code="already_deactivated",
                    description="Пользователь уже деактивирован",
                    type=ErrorType.CONFLICT,
                )
            )

        self.is_active = False
        self.add_domain_event(Deactivated(user_id=self.id))
        return Result.ok(None)

    def activate(self) -> Result[None]:
        if self.is_active:
            return Result.fail(
                Error(
                    code="already_active",
                    description="Пользователь уже активен",
                    type=ErrorType.CONFLICT,
                )
            )

        self.is_active = True
        self.add_domain_event(Activated(user_id=self.id))
        return Result.ok(None)
