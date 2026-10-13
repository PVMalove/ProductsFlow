"""Реализация транзакционной границы inventory на SQLAlchemy."""

from kernel_platform.unit_of_work import SqlAlchemyUnitOfWork
from sqlalchemy.ext.asyncio import AsyncSession

from domain.repositories import InventoryRepository
from domain.unit_of_work import InventoryUnitOfWork
from infrastructure.db.inventory_repository import (
    InventoryRepository as SqlInventoryRepository,
)


class SqlInventoryUnitOfWork(SqlAlchemyUnitOfWork):
    def __init__(self, session: AsyncSession) -> None:
        super().__init__(session)
        self.inventory: InventoryRepository = SqlInventoryRepository(session)


_inventory_unit_of_work_implementation: type[InventoryUnitOfWork] = (
    SqlInventoryUnitOfWork
)
