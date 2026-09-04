"""Adapter совместимости для до-CQRS пути импорта деактивации."""

from application.commands.deactivate_user import (
    ActivateUserCommand,
    ActivateUserCommandHandler,
    DeactivateUserCommand,
    DeactivateUserCommandHandler,
)

__all__ = [
    "ActivateUserCommand",
    "ActivateUserCommandHandler",
    "DeactivateUserCommand",
    "DeactivateUserCommandHandler",
]
