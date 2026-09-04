"""SQLAlchemy implementation of the catalog transaction boundary."""

from kernel_platform.unit_of_work import SqlAlchemyUnitOfWork
from sqlalchemy.ext.asyncio import AsyncSession

from domain.repositories import ProductRepository
from domain.unit_of_work import CatalogUnitOfWork
from infrastructure.db.product_repository import (
    ProductRepository as SqlProductRepository,
)


class SqlCatalogUnitOfWork(SqlAlchemyUnitOfWork):
    def __init__(self, session: AsyncSession) -> None:
        super().__init__(session)
        self.products: ProductRepository = SqlProductRepository(session)


_catalog_unit_of_work_implementation: type[CatalogUnitOfWork] = SqlCatalogUnitOfWork
