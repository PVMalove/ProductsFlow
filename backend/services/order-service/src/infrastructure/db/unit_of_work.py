"""Реализация транзакционной границы cart на SQLAlchemy."""

from kernel_platform.unit_of_work import SqlAlchemyUnitOfWork
from sqlalchemy.ext.asyncio import AsyncSession

from domain.repositories import CartRepository
from domain.unit_of_work import CartUnitOfWork
from infrastructure.db.cart_repository import CartRepository as SqlCartRepository


class SqlCartUnitOfWork(SqlAlchemyUnitOfWork):
    def __init__(self, session: AsyncSession) -> None:
        super().__init__(session)
        self.carts: CartRepository = SqlCartRepository(session)


_cart_unit_of_work_implementation: type[CartUnitOfWork] = SqlCartUnitOfWork
