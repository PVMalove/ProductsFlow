"""Реализация транзакционной границы payment на SQLAlchemy."""

from kernel_platform.unit_of_work import SqlAlchemyUnitOfWork
from sqlalchemy.ext.asyncio import AsyncSession

from domain.repositories import PaymentAuthorizationRepository
from domain.unit_of_work import PaymentUnitOfWork
from infrastructure.db.payment_repository import (
    PaymentAuthorizationRepository as SqlPaymentAuthorizationRepository,
)


class SqlPaymentUnitOfWork(SqlAlchemyUnitOfWork):
    def __init__(self, session: AsyncSession) -> None:
        super().__init__(session)
        self.payments: PaymentAuthorizationRepository = (
            SqlPaymentAuthorizationRepository(session)
        )


_payment_unit_of_work_implementation: type[PaymentUnitOfWork] = SqlPaymentUnitOfWork
