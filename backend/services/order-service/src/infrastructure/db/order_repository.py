import uuid

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from domain.entities.order import Order, OrderLine, OrderSagaStep, OrderStatus
from domain.repositories import OrderRepository as OrderRepositoryPort
from infrastructure.db.entity_configurations.models import (
    OrderLineModel,
    OrderModel,
    OrderSagaTransitionModel,
)


class OrderRepository:
    """CRUD для `Order`/`OrderLine` (issue #372). `save` — diff-based, тот же
    приём, что `CartRepository.save` (issue #369): набор строк только
    сокращается после создания (D7), никогда не растёт. issue #376, D5:
    `save` дописывает строку `order_saga_transitions` на создание Order и на
    каждое изменение `(saga_step, status)` — в той же транзакции."""

    def __init__(self, session: AsyncSession) -> None:
        self.session = session

    async def get_by_id(self, order_id: uuid.UUID) -> Order | None:
        row = await self.session.scalar(
            select(OrderModel).where(OrderModel.id == order_id)
        )
        if row is None:
            return None
        return await self._to_domain(row)

    async def save(self, order: Order) -> None:
        existing_row = await self.session.scalar(
            select(OrderModel).where(OrderModel.id == order.id)
        )
        if existing_row is None:
            self.session.add(
                OrderModel(
                    id=order.id,
                    user_id=order.user_id,
                    status=order.status.value,
                    saga_step=order.saga_step.value,
                    failure_reason=order.failure_reason,
                    created_at=order.created_at,
                    payment_authorization_id=order.payment_authorization_id,
                )
            )
            self._journal_transition(order)
        else:
            # issue #376, D5: сравнение — ДО присваивания новых значений.
            if (existing_row.saga_step, existing_row.status) != (
                order.saga_step.value,
                order.status.value,
            ):
                self._journal_transition(order)
            existing_row.status = order.status.value
            existing_row.saga_step = order.saga_step.value
            existing_row.failure_reason = order.failure_reason
            existing_row.payment_authorization_id = order.payment_authorization_id

        existing_line_rows = {
            row.id: row
            for row in (
                await self.session.scalars(
                    select(OrderLineModel).where(OrderLineModel.order_id == order.id)
                )
            ).all()
        }
        domain_line_ids = {line.id for line in order.lines}
        for row_id, row in existing_line_rows.items():
            if row_id not in domain_line_ids:
                await self.session.delete(row)

        for line in order.lines:
            if line.id not in existing_line_rows:
                self.session.add(
                    OrderLineModel(
                        id=line.id,
                        order_id=order.id,
                        product_id=line.product_id,
                        quantity=line.quantity,
                        unit_price_kopecks=line.unit_price_kopecks,
                    )
                )

    def _journal_transition(self, order: Order) -> None:
        self.session.add(
            OrderSagaTransitionModel(
                order_id=order.id,
                saga_step=order.saga_step.value,
                status=order.status.value,
            )
        )

    async def _to_domain(self, row: OrderModel) -> Order:
        line_rows = list(
            (
                await self.session.scalars(
                    select(OrderLineModel)
                    .where(OrderLineModel.order_id == row.id)
                    .order_by(OrderLineModel.id.asc())
                )
            ).all()
        )
        return Order.reconstitute(
            row.id,
            user_id=row.user_id,
            status=OrderStatus(row.status),
            saga_step=OrderSagaStep(row.saga_step),
            lines=[
                OrderLine(
                    id=line_row.id,
                    product_id=line_row.product_id,
                    quantity=line_row.quantity,
                    unit_price_kopecks=line_row.unit_price_kopecks,
                )
                for line_row in line_rows
            ],
            failure_reason=row.failure_reason,
            created_at=row.created_at,
            payment_authorization_id=row.payment_authorization_id,
        )


# Статическая структурная проверка (мирует `cart_repository.py`).
_order_repository_implementation: type[OrderRepositoryPort] = OrderRepository
