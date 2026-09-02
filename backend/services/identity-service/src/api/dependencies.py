from typing import Annotated

from fastapi import Depends

from application.commands import (
    ActivateUserCommandHandler,
    ChangePasswordCommandHandler,
    DeactivateUserCommandHandler,
    LoginCommandHandler,
    RegisterUserCommandHandler,
)
from application.ports import (
    PasswordHasher,
    UserAuditQueryPort,
    UserListQueryPort,
    UserQueryPort,
)
from application.queries import (
    GetUserAuditQueryHandler,
    ListUsersQueryHandler,
)
from domain.repositories import UserRepository
from infrastructure.db.audit import SqlUserAuditReader
from infrastructure.db.session import DbSessionDI
from infrastructure.db.user_repository import (
    SqlUserQueryRepository,
)
from infrastructure.db.user_repository import (
    UserRepository as SqlUserRepository,
)
from infrastructure.security.password_hasher import BcryptPasswordHasher


def get_user_repository(session: DbSessionDI) -> SqlUserRepository:
    return SqlUserRepository(session)


UserRepositoryDI = Annotated[UserRepository, Depends(get_user_repository)]


def get_user_query_repository(session: DbSessionDI) -> SqlUserQueryRepository:
    return SqlUserQueryRepository(session)


UserQueryRepositoryDI = Annotated[UserQueryPort, Depends(get_user_query_repository)]
UserListRepositoryDI = Annotated[UserListQueryPort, Depends(get_user_query_repository)]


def get_user_audit_reader(session: DbSessionDI) -> SqlUserAuditReader:
    return SqlUserAuditReader(session)


UserAuditReaderDI = Annotated[UserAuditQueryPort, Depends(get_user_audit_reader)]


def get_password_hasher() -> PasswordHasher:
    return BcryptPasswordHasher()


PasswordHasherDI = Annotated[PasswordHasher, Depends(get_password_hasher)]


def get_register_handler(
    repository: UserRepositoryDI, hasher: PasswordHasherDI
) -> RegisterUserCommandHandler:
    return RegisterUserCommandHandler(repository, hasher)


RegisterUserDI = Annotated[RegisterUserCommandHandler, Depends(get_register_handler)]


def get_login_handler(
    repository: UserRepositoryDI, hasher: PasswordHasherDI
) -> LoginCommandHandler:
    return LoginCommandHandler(repository, hasher)


LoginDI = Annotated[LoginCommandHandler, Depends(get_login_handler)]


def get_change_password_handler(
    repository: UserRepositoryDI, hasher: PasswordHasherDI
) -> ChangePasswordCommandHandler:
    return ChangePasswordCommandHandler(repository, hasher)


ChangePasswordDI = Annotated[
    ChangePasswordCommandHandler, Depends(get_change_password_handler)
]


def get_activate_handler(
    repository: UserRepositoryDI,
) -> ActivateUserCommandHandler:
    return ActivateUserCommandHandler(repository)


ActivateUserDI = Annotated[ActivateUserCommandHandler, Depends(get_activate_handler)]


def get_deactivate_handler(
    repository: UserRepositoryDI,
) -> DeactivateUserCommandHandler:
    return DeactivateUserCommandHandler(repository)


DeactivateUserDI = Annotated[
    DeactivateUserCommandHandler, Depends(get_deactivate_handler)
]


def get_list_users_handler(
    repository: UserListRepositoryDI,
) -> ListUsersQueryHandler:
    return ListUsersQueryHandler(repository)


ListUsersDI = Annotated[ListUsersQueryHandler, Depends(get_list_users_handler)]


def get_user_audit_handler(
    reader: UserAuditReaderDI,
) -> GetUserAuditQueryHandler:
    return GetUserAuditQueryHandler(reader)


UserAuditDI = Annotated[GetUserAuditQueryHandler, Depends(get_user_audit_handler)]


__all__ = [
    "ActivateUserDI",
    "ChangePasswordDI",
    "DeactivateUserDI",
    "DbSessionDI",
    "ListUsersDI",
    "LoginDI",
    "PasswordHasherDI",
    "RegisterUserDI",
    "UserAuditDI",
    "UserAuditReaderDI",
    "UserQueryRepositoryDI",
    "UserRepositoryDI",
    "get_user_repository",
]
