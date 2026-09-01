"""Identity command DTOs and their application handlers."""

from dataclasses import dataclass

from kernel_domain.errors import Error, ErrorType
from kernel_domain.result import Result

from application.ports import PasswordHasher
from domain.email import Email
from domain.raw_password import RawPassword
from domain.repositories import UserRepository
from domain.user import User
from domain.user_id import UserId


@dataclass(frozen=True)
class RegisterUserCommand:
    email: str
    password: str


class RegisterUserCommandHandler:
    def __init__(self, users: UserRepository, password_hasher: PasswordHasher) -> None:
        self._users = users
        self._password_hasher = password_hasher

    def handle(self, command: RegisterUserCommand) -> Result[User]:
        email = Email(command.email)
        if self._users.exists_by_email(email):
            return Result.fail(
                Error(
                    code="email_already_registered",
                    description=f"Email {command.email!r} уже зарегистрирован",
                    type=ErrorType.CONFLICT,
                )
            )
        password = RawPassword.create(command.password)
        if password.is_err:
            return Result.fail(password.error)
        result = User.register(email, self._password_hasher.hash(password.value.value))
        if result.is_ok:
            self._users.add(result.value)
        return result


@dataclass(frozen=True)
class LoginCommand:
    email: str
    password: str


class LoginCommandHandler:
    def __init__(self, users: UserRepository, password_hasher: PasswordHasher) -> None:
        self._users = users
        self._password_hasher = password_hasher

    def handle(self, command: LoginCommand) -> Result[User]:
        user = self._users.get_by_email(Email(command.email))
        if user is None or not self._password_hasher.verify(
            command.password, user.password_hash
        ):
            return Result.fail(
                Error(
                    code="invalid_credentials",
                    description="Неверный email или пароль",
                    type=ErrorType.UNAUTHORIZED,
                )
            )
        if not user.is_active:
            return Result.fail(
                Error(
                    code="user_deactivated",
                    description="Пользователь деактивирован",
                    type=ErrorType.FORBIDDEN,
                )
            )
        return Result.ok(user)


@dataclass(frozen=True)
class ChangePasswordCommand:
    user_id: UserId
    old_password: str
    new_password: str


class ChangePasswordCommandHandler:
    def __init__(self, users: UserRepository, password_hasher: PasswordHasher) -> None:
        self._users = users
        self._password_hasher = password_hasher

    def handle(self, command: ChangePasswordCommand) -> Result[User]:
        user = self._users.get_by_id(command.user_id)
        if user is None or not self._password_hasher.verify(
            command.old_password, user.password_hash
        ):
            return Result.fail(
                Error(
                    code="invalid_credentials",
                    description="Текущий пароль не совпадает",
                    type=ErrorType.UNAUTHORIZED,
                )
            )
        password = RawPassword.create(command.new_password)
        if password.is_err:
            return Result.fail(password.error)
        result = user.change_password(self._password_hasher.hash(password.value.value))
        if result.is_err:
            return Result.fail(result.error)
        self._users.save(user)
        return Result.ok(user)


@dataclass(frozen=True)
class DeactivateUserCommand:
    target_user_id: UserId
    actor_user_id: UserId


class DeactivateUserCommandHandler:
    def __init__(self, users: UserRepository) -> None:
        self._users = users

    def handle(self, command: DeactivateUserCommand) -> Result[User]:
        if command.target_user_id == command.actor_user_id:
            return Result.fail(
                Error(
                    code="cannot_deactivate_self",
                    description="Пользователь не может деактивировать самого себя",
                    type=ErrorType.FORBIDDEN,
                )
            )
        user = self._users.get_by_id(command.target_user_id)
        if user is None:
            return Result.fail(
                Error(
                    code="user_not_found",
                    description="Пользователь не найден",
                    type=ErrorType.NOT_FOUND,
                )
            )
        result = user.deactivate()
        if result.is_err:
            return Result.fail(result.error)
        self._users.save(user)
        return Result.ok(user)


@dataclass(frozen=True)
class ActivateUserCommand:
    target_user_id: UserId


class ActivateUserCommandHandler:
    def __init__(self, users: UserRepository) -> None:
        self._users = users

    def handle(self, command: ActivateUserCommand) -> Result[User]:
        user = self._users.get_by_id(command.target_user_id)
        if user is None:
            return Result.fail(
                Error(
                    code="user_not_found",
                    description="Пользователь не найден",
                    type=ErrorType.NOT_FOUND,
                )
            )
        result = user.activate()
        if result.is_err:
            return Result.fail(result.error)
        self._users.save(user)
        return Result.ok(user)
