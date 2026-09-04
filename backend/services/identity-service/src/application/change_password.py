"""Adapter совместимости для до-CQRS пути импорта смены пароля."""

from application.commands.change_password import (
    ChangePasswordCommand,
    ChangePasswordCommandHandler,
)

__all__ = ["ChangePasswordCommand", "ChangePasswordCommandHandler"]
