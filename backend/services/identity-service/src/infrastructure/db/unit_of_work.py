"""Реализация транзакционной границы identity на SQLAlchemy."""

from kernel_platform.unit_of_work import SqlAlchemyUnitOfWork
from sqlalchemy.ext.asyncio import AsyncSession

from domain.repositories import UserRepository
from domain.unit_of_work import IdentityUnitOfWork
from infrastructure.db.user_repository import UserRepository as SqlUserRepository


class SqlIdentityUnitOfWork(SqlAlchemyUnitOfWork):
    def __init__(self, session: AsyncSession) -> None:
        super().__init__(session)
        self.users: UserRepository = SqlUserRepository(session)


_identity_unit_of_work_implementation: type[IdentityUnitOfWork] = SqlIdentityUnitOfWork
