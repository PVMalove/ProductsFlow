from dataclasses import dataclass

from kernel_domain.errors import Error, ErrorType
from kernel_domain.result import Result

from domain.repositories import UserRepository
from domain.user import User
from domain.user_id import UserId

_CANNOT_SELF_DEACTIVATE = Error(
    code="cannot_deactivate_self",
    description="Пользователь не может деактивировать самого себя",
    type=ErrorType.FORBIDDEN,
)

_USER_NOT_FOUND = Error(
    code="user_not_found",
    description="Пользователь не найден",
    type=ErrorType.NOT_FOUND,
)


@dataclass(frozen=True)
class DeactivateUserCommand:
    """Деактивация пользователя (ADR TD-01 Фаза 1) — self-deactivation
    отклоняется здесь, до обращения к агрегату: `User.deactivate()` не
    знает, кто именно выполняет операцию."""

    target_user_id: UserId
    actor_user_id: UserId


class DeactivateUserCommandHandler:
    def __init__(self, user_repository: UserRepository) -> None:
        self._user_repository = user_repository

    def handle(self, command: DeactivateUserCommand) -> Result[User]:
        if command.target_user_id == command.actor_user_id:
            return Result.fail(_CANNOT_SELF_DEACTIVATE)

        user = self._user_repository.get_by_id(command.target_user_id)
        if user is None:
            return Result.fail(_USER_NOT_FOUND)

        result = user.deactivate()
        if result.is_err:
            return Result.fail(result.error)

        self._user_repository.save(user)
        return Result.ok(user)
