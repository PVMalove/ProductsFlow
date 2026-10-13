"""Реализация транзакционной границы payment на SQLAlchemy."""

from types import TracebackType

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


class PaymentCommandUnitOfWork(SqlAlchemyUnitOfWork):
    """UnitOfWork для `AuthorizePaymentCommandHandler`/`VoidPaymentCommandHandler`,
    когда их вызывает message-driven адаптер (issue #371, архитектурный бриф
    D5) изнутри `consume_command`'s собственного `async with session.begin():`.
    Базовые `commit()`/`__aexit__` (`kernel_platform/unit_of_work.py`) трогают
    сессию напрямую (`session.commit()`/`session.rollback()`) — обе операции
    конфликтуют с транзакцией, которой уже управляет `consume_command`. Оба
    метода ниже — no-op на сессии: `commit()` только помечает границу
    закрытой (сохраняя `async with self._uow: ... await self._uow.commit()`
    форму существующих хендлеров БУКВАЛЬНО без изменений); `__aexit__` никогда
    не трогает сессию — исключение, если оно есть, долетает нетронутым до
    `consume_command`'s `session.begin()`, который делает единственный
    настоящий rollback. Доказано эмпирически интеграционным тестом
    `tests/integration/test_payment_outbox_inbox_atomicity.py` (Seams for
    TDD #1)."""

    def __init__(self, session: AsyncSession) -> None:
        super().__init__(session)
        self.payments: PaymentAuthorizationRepository = (
            SqlPaymentAuthorizationRepository(session)
        )

    async def commit(self) -> None:
        self._committed = True

    async def __aexit__(
        self,
        _exc_type: type[BaseException] | None,
        _exc: BaseException | None,
        _tb: TracebackType | None,
    ) -> None:
        return None
