"""Compatibility adapter for the pre-CQRS password-change import path."""

from application.commands.change_password import (
    ChangePasswordCommand,
    ChangePasswordCommandHandler,
)

__all__ = ["ChangePasswordCommand", "ChangePasswordCommandHandler"]
