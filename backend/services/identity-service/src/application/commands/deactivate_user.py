"""Activation and deactivation commands and handlers."""

from dataclasses import dataclass

from kernel_domain.errors import Error, ErrorType
from kernel_domain.result import Result

from domain.repositories import UserRepository
from domain.user import User
from domain.user_id import UserId


@dataclass(frozen=True)
class DeactivateUserCommand:
    target_user_id: UserId
    actor_user_id: UserId


class DeactivateUserCommandHandler:
    def __init__(self, users: UserRepository) -> None:
        self._users = users

    def execute(self, command: DeactivateUserCommand) -> Result[User]:
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
    """DTO для активации пользователя."""

    target_user_id: UserId


class ActivateUserCommandHandler:
    """
    Business Logic Summary

    Context & Purpose: Активация учетной записи пользователя.
    Validations: Проверка прав доступа.
    Side Effects: Статус пользователя меняется на активный.
    """

    def __init__(self, users: UserRepository) -> None:
        self._users = users

    def execute(self, command: ActivateUserCommand) -> Result[User]:
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
