"""Реализация транзакционной границы cart/checkout на SQLAlchemy."""

from kernel_platform.unit_of_work import SqlAlchemyUnitOfWork
from sqlalchemy.ext.asyncio import AsyncSession

from domain.repositories import (
    CartRepository,
    IdempotencyKeyRepository,
    OrderRepository,
    SagaCommandOutboxRepository,
)
from domain.unit_of_work import CartUnitOfWork, CheckoutUnitOfWork
from infrastructure.db.cart_repository import CartRepository as SqlCartRepository
from infrastructure.db.idempotency_key_repository import (
    IdempotencyKeyRepository as SqlIdempotencyKeyRepository,
)
from infrastructure.db.order_repository import OrderRepository as SqlOrderRepository
from infrastructure.db.saga_command_outbox_repository import (
    SagaCommandOutboxRepository as SqlSagaCommandOutboxRepository,
)


class SqlCartUnitOfWork(SqlAlchemyUnitOfWork):
    """Один конкретный класс удовлетворяет и `CartUnitOfWork` (issue #369),
    и `CheckoutUnitOfWork` (issue #372, D5) — все репозитории делят одну
    сессию/транзакцию, отдельный класс на каждый Protocol был бы чистой
    дупликацией переиспользуемой bookkeeping-обвязки."""

    def __init__(self, session: AsyncSession) -> None:
        super().__init__(session)
        self.carts: CartRepository = SqlCartRepository(session)
        self.orders: OrderRepository = SqlOrderRepository(session)
        self.idempotency_keys: IdempotencyKeyRepository = SqlIdempotencyKeyRepository(
            session
        )
        self.saga_command_outbox: SagaCommandOutboxRepository = (
            SqlSagaCommandOutboxRepository(session)
        )


_cart_unit_of_work_implementation: type[CartUnitOfWork] = SqlCartUnitOfWork
_checkout_unit_of_work_implementation: type[CheckoutUnitOfWork] = SqlCartUnitOfWork
