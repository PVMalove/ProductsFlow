"""Compatibility adapter for the pre-CQRS deactivation import path."""

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
