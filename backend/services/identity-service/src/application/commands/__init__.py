"""Public command-side interface for identity application use cases."""

from application.commands.activate_user import (
    ActivateUserCommand,
    ActivateUserCommandHandler,
)
from application.commands.change_password import (
    ChangePasswordCommand,
    ChangePasswordCommandHandler,
)
from application.commands.change_role import (
    ChangeUserRoleCommand,
    ChangeUserRoleCommandHandler,
)
from application.commands.deactivate_user import (
    DeactivateUserCommand,
    DeactivateUserCommandHandler,
)
from application.commands.delete_account import (
    DeleteAccountCommand,
    DeleteAccountCommandHandler,
)
from application.commands.login import LoginCommand, LoginCommandHandler
from application.commands.register_user import (
    RegisterUserCommand,
    RegisterUserCommandHandler,
)

__all__ = [
    "ActivateUserCommand",
    "ActivateUserCommandHandler",
    "ChangePasswordCommand",
    "ChangePasswordCommandHandler",
    "ChangeUserRoleCommand",
    "ChangeUserRoleCommandHandler",
    "DeactivateUserCommand",
    "DeactivateUserCommandHandler",
    "DeleteAccountCommand",
    "DeleteAccountCommandHandler",
    "LoginCommand",
    "LoginCommandHandler",
    "RegisterUserCommand",
    "RegisterUserCommandHandler",
]
