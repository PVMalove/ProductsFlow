"""Adapter совместимости для до-CQRS пути импорта логина."""

from application.commands.login import LoginCommand, LoginCommandHandler

__all__ = ["LoginCommand", "LoginCommandHandler"]
