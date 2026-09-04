"""Adapter совместимости для до-CQRS пути импорта register-user."""

from application.commands.register_user import (
    RegisterUserCommand,
    RegisterUserCommandHandler,
)

__all__ = ["RegisterUserCommand", "RegisterUserCommandHandler"]
