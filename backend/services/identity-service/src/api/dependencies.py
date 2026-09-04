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
    GetCurrentUserHandler,
    GetUserAuditQueryHandler,
    ListUsersQueryHandler,
)
from domain.repositories import UserRepository
from domain.unit_of_work import IdentityUnitOfWork
from infrastructure.db.audit import SqlUserAuditReader
from infrastructure.db.session import DbSessionDI
from infrastructure.db.unit_of_work import SqlIdentityUnitOfWork
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


def get_identity_uow(session: DbSessionDI) -> IdentityUnitOfWork:
    return SqlIdentityUnitOfWork(session)


IdentityUnitOfWorkDI = Annotated[IdentityUnitOfWork, Depends(get_identity_uow)]


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
    uow: IdentityUnitOfWorkDI, hasher: PasswordHasherDI
) -> RegisterUserCommandHandler:
    return RegisterUserCommandHandler(uow, hasher)


RegisterUserDI = Annotated[RegisterUserCommandHandler, Depends(get_register_handler)]


def get_login_handler(
    uow: IdentityUnitOfWorkDI, hasher: PasswordHasherDI
) -> LoginCommandHandler:
    return LoginCommandHandler(uow, hasher)


LoginDI = Annotated[LoginCommandHandler, Depends(get_login_handler)]


def get_change_password_handler(
    uow: IdentityUnitOfWorkDI, hasher: PasswordHasherDI
) -> ChangePasswordCommandHandler:
    return ChangePasswordCommandHandler(uow, hasher)


ChangePasswordDI = Annotated[
    ChangePasswordCommandHandler, Depends(get_change_password_handler)
]


def get_activate_handler(
    uow: IdentityUnitOfWorkDI,
) -> ActivateUserCommandHandler:
    return ActivateUserCommandHandler(uow)


ActivateUserDI = Annotated[ActivateUserCommandHandler, Depends(get_activate_handler)]


def get_deactivate_handler(
    uow: IdentityUnitOfWorkDI,
) -> DeactivateUserCommandHandler:
    return DeactivateUserCommandHandler(uow)


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
    users: UserQueryRepositoryDI,
) -> GetUserAuditQueryHandler:
    return GetUserAuditQueryHandler(reader, users)


UserAuditDI = Annotated[GetUserAuditQueryHandler, Depends(get_user_audit_handler)]


def get_current_user_handler(
    users: UserQueryRepositoryDI,
) -> GetCurrentUserHandler:
    return GetCurrentUserHandler(users)


GetCurrentUserDI = Annotated[GetCurrentUserHandler, Depends(get_current_user_handler)]


__all__ = [
    "ActivateUserDI",
    "ChangePasswordDI",
    "DeactivateUserDI",
    "DbSessionDI",
    "GetCurrentUserDI",
    "IdentityUnitOfWorkDI",
    "ListUsersDI",
    "LoginDI",
    "PasswordHasherDI",
    "RegisterUserDI",
    "UserAuditDI",
    "UserAuditReaderDI",
    "UserQueryRepositoryDI",
    "UserRepositoryDI",
    "get_identity_uow",
    "get_user_repository",
]
