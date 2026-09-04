"""Команда и handler activate-user."""

from dataclasses import dataclass

from kernel_domain.errors import Error, ErrorType
from kernel_domain.result import Result

from contracts.user import UserView
from domain.unit_of_work import IdentityUnitOfWork
from domain.value_objects.user_id import UserId


@dataclass(frozen=True)
class ActivateUserCommand:
    """DTO для активации пользователя."""

    target_user_id: UserId


class ActivateUserCommandHandler:
    """Активирует деактивированную учётную запись и сохраняет агрегат."""

    def __init__(self, uow: IdentityUnitOfWork) -> None:
        self._uow = uow

    async def execute(self, command: ActivateUserCommand) -> Result[UserView]:
        async with self._uow:
            user = await self._uow.users.get_by_id(command.target_user_id)
            if user is None:
                return Result[UserView].fail(
                    Error(
                        code="user_not_found",
                        description="Пользователь не найден",
                        type=ErrorType.NOT_FOUND,
                    )
                )
            result = user.activate()
            if result.is_err:
                return Result[UserView].fail(result.error)
            await self._uow.users.save(user)
            await self._uow.commit()
            return Result[UserView].ok(UserView.from_user(user))
