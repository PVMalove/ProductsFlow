"""Compatibility adapter for the pre-CQRS register-user import path."""

from application.commands.register_user import (
    RegisterUserCommand,
    RegisterUserCommandHandler,
)

__all__ = ["RegisterUserCommand", "RegisterUserCommandHandler"]
