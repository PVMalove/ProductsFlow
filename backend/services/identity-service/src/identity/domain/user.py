from kernel_domain.entity import Entity
from kernel_domain.result import Result

from identity.domain.email import Email
from identity.domain.events import UserRegistered
from identity.domain.role import Role
from identity.domain.user_id import UserId


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
