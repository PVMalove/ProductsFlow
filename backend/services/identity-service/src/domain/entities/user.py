from typing import cast

from kernel_domain import PRIVATE_MARKER
from kernel_domain.entity import Entity
from kernel_domain.errors import Error, ErrorType
from kernel_domain.result import Result

from domain.events.user_domain_event import (
    Activated,
    Deactivated,
    Deleted,
    PasswordChanged,
    RoleChanged,
    UserRegistered,
)
from domain.role import Role
from domain.value_objects.email import Email
from domain.value_objects.user_id import UserId

_MISSING = object()


class User(Entity[UserId]):
    """Агрегат учётной записи (ADR TD-01 Фаза 1). Не видит plaintext-пароль
    и не занимается хешированием — `password_hash` приходит уже вычисленным
    от вызывающего слоя (`PasswordHasher`-порт). Стойкость исходного пароля
    проверяется раньше, доменным VO `RawPassword`, не здесь — `password_hash`
    как таковой не несёт признаков, по которым эту стойкость можно было бы
    осмысленно перепроверить.

    Конструктор вызывается только через `register()` (новый пользователь) или
    `reconstitute()` (гидратация из БД) — маркер приватности проверяется
    централизованно в `Entity.__init__`."""

    def __init__(
        self,
        marker: object = _MISSING,
        id: UserId = cast("UserId", _MISSING),
        *,
        email: Email,
        password_hash: str,
        role: Role,
        is_active: bool,
        is_deleted: bool = False,
    ) -> None:
        super().__init__(marker, id=id)
        self.email = email
        self.password_hash = password_hash
        self.role = role
        self.is_active = is_active
        self.is_deleted = is_deleted

    @classmethod
    def register(cls, email: Email, password_hash: str) -> Result["User"]:
        user = cls(
            PRIVATE_MARKER,
            UserId.new_id(),
            email=email,
            password_hash=password_hash,
            role=Role.USER,
            is_active=True,
        )
        user.add_domain_event(UserRegistered(user_id=user.id, email=email))
        return Result[User].ok(user)

    @classmethod
    def reconstitute(
        cls,
        id: UserId,
        *,
        email: Email,
        password_hash: str,
        role: Role,
        is_active: bool,
        is_deleted: bool = False,
    ) -> "User":
        return cls(
            PRIVATE_MARKER,
            id,
            email=email,
            password_hash=password_hash,
            role=role,
            is_active=is_active,
            is_deleted=is_deleted,
        )

    def change_password(self, new_password_hash: str) -> Result[None]:
        if not self.is_active:
            return Result[None].fail(
                Error(
                    code="user_deactivated",
                    description="Деактивированный пользователь не может сменить пароль",
                    type=ErrorType.FORBIDDEN,
                )
            )

        self.password_hash = new_password_hash
        self.add_domain_event(PasswordChanged(user_id=self.id))
        return Result[None].ok(None)

    def deactivate(self) -> Result[None]:
        if not self.is_active:
            return Result[None].fail(
                Error(
                    code="already_deactivated",
                    description="Пользователь уже деактивирован",
                    type=ErrorType.CONFLICT,
                )
            )

        self.is_active = False
        self.add_domain_event(Deactivated(user_id=self.id))
        return Result[None].ok(None)

    def activate(self) -> Result[None]:
        if self.is_deleted:
            return Result[None].fail(
                Error(
                    code="user_deleted",
                    description="Удалённая учётная запись не может быть активирована",
                    type=ErrorType.FORBIDDEN,
                )
            )
        if self.is_active:
            return Result[None].fail(
                Error(
                    code="already_active",
                    description="Пользователь уже активен",
                    type=ErrorType.CONFLICT,
                )
            )

        self.is_active = True
        self.add_domain_event(Activated(user_id=self.id))
        return Result[None].ok(None)

    def delete(self) -> Result[None]:
        """Заменяет эту учётную запись анонимизированным терминальным
        tombstone (ADR 0007). Старый email освобождается для новой
        регистрации — удаление легитимный исход identity-домена, не
        замаскированная деактивация — а `is_deleted` навсегда блокирует
        реактивацию."""
        if self.is_deleted:
            return Result[None].fail(
                Error(
                    code="already_deleted",
                    description="Учётная запись уже удалена",
                    type=ErrorType.CONFLICT,
                )
            )

        anonymized_email = Email.create(f"deleted-{self.id.value}@tombstone.invalid")
        assert anonymized_email.is_ok, "generated tombstone email must be valid"
        self.email = anonymized_email.value
        self.password_hash = "!deleted-account!"
        self.is_active = False
        self.is_deleted = True
        self.add_domain_event(Deleted(user_id=self.id))
        return Result[None].ok(None)

    def change_role(self, role: Role) -> Result[None]:
        if self.role == role:
            return Result[None].fail(
                Error(
                    code="role_unchanged",
                    description=f"Пользователь уже имеет роль {role.value!r}",
                    type=ErrorType.CONFLICT,
                )
            )

        self.role = role
        self.add_domain_event(RoleChanged(user_id=self.id, role=role))
        return Result[None].ok(None)
