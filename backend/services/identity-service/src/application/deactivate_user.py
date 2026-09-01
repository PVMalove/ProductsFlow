"""Compatibility adapter for the pre-CQRS deactivation import path."""

from application.commands import DeactivateUserCommand, DeactivateUserCommandHandler

__all__ = ["DeactivateUserCommand", "DeactivateUserCommandHandler"]
