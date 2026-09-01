"""Compatibility adapter for the pre-CQRS login import path."""

from application.commands import LoginCommand, LoginCommandHandler

__all__ = ["LoginCommand", "LoginCommandHandler"]
