import uuid

from kernel_domain.result import Result
from kernel_platform.outbox.drain import drain_events_to_outbox
from sqlalchemy import select
from sqlalchemy.dialects.postgresql import insert as pg_insert
from sqlalchemy.ext.asyncio import AsyncSession

from domain.entities.inventory import Inventory
from domain.repositories import (
    InventoryRepository as InventoryRepositoryPort,
)
from infrastructure.db.entity_configurations.models import InventoryModel


def _to_domain(row: InventoryModel) -> Inventory:
    return Inventory.reconstitute(row.product_id, quantity=row.quantity)


class InventoryRepository:
    """CRUD для `Inventory` (issue #367). Мутирующие методы дренируют
    доменные события в outbox в точке мутации; фиксация транзакции
    принадлежит `InventoryUnitOfWork` (ADR 0006) — этот адаптер никогда не
    коммитит самостоятельно."""

    def __init__(self, session: AsyncSession) -> None:
        self.session = session

    async def get_by_product_id(self, product_id: uuid.UUID) -> Inventory | None:
        row = await self.session.get(InventoryModel, product_id)
        return _to_domain(row) if row is not None else None

    async def create_zero(self, product_id: uuid.UUID) -> bool:
        inventory = Inventory.create_zero(product_id)
        inserted_id = await self.session.scalar(
            pg_insert(InventoryModel)
            .values(product_id=inventory.id, quantity=inventory.quantity)
            .on_conflict_do_nothing(index_elements=[InventoryModel.product_id])
            .returning(InventoryModel.product_id)
        )
        if inserted_id is None:
            return False
        # `create_zero()` не добавляет доменных событий сегодня (Trade-offs
        # брифа #367) — вызов остаётся здесь ради симметрии с `adjust()` и
        # на случай, если это когда-нибудь изменится.
        await drain_events_to_outbox(self.session, inventory)
        return True

    async def adjust(
        self, product_id: uuid.UUID, delta: int, *, reason: str
    ) -> Result[Inventory] | None:
        row = await self.session.scalar(
            select(InventoryModel)
            .where(InventoryModel.product_id == product_id)
            .with_for_update()
        )
        if row is None:
            return None

        inventory = _to_domain(row)
        result = inventory.adjust(delta)
        if result.is_err:
            return Result[Inventory].fail(result.error)

        row.quantity = inventory.quantity
        row.pending_audit_reason = reason
        await drain_events_to_outbox(self.session, inventory)
        return Result[Inventory].ok(inventory)


# Статическая структурная проверка: mypy убеждается, что конкретная
# реализация удовлетворяет каждую операцию, требуемую доменным контрактом
# репозитория.
_inventory_repository_implementation: type[InventoryRepositoryPort] = (
    InventoryRepository
)
