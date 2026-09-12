import uuid
from datetime import UTC, datetime

from sqlalchemy import select
from sqlalchemy.dialects.postgresql import insert as pg_insert
from sqlalchemy.ext.asyncio import AsyncSession

from domain.entities.cart import Cart
from domain.entities.cart_line import CartLine
from domain.repositories import CartRepository as CartRepositoryPort
from domain.value_objects.cart_id import CartId
from infrastructure.db.entity_configurations.models import CartLineModel, CartModel


class CartRepository:
    """CRUD для `Cart`/`CartLine` (issue #369). Никакого outbox-дренажа —
    order-service не эмитит доменных событий в этом тикете (архитектурный
    бриф D1); фиксация транзакции принадлежит `CartUnitOfWork` (ADR 0006) —
    этот адаптер никогда не коммитит самостоятельно."""

    def __init__(self, session: AsyncSession) -> None:
        self.session = session

    async def get_or_create_for_user(self, user_id: uuid.UUID) -> Cart:
        # D3: атомарный get-or-create — INSERT ... ON CONFLICT(user_id) DO
        # NOTHING, затем повторное чтение (с блокировкой строки под мутацию)
        # — закрывает TOCTOU-гонку двух конкурентных первых AddCartLine.
        await self.session.execute(
            pg_insert(CartModel)
            .values(id=uuid.uuid4(), user_id=user_id, created_at=datetime.now(UTC))
            .on_conflict_do_nothing(index_elements=[CartModel.user_id])
        )
        row = await self.session.scalar(
            select(CartModel).where(CartModel.user_id == user_id).with_for_update()
        )
        assert row is not None, "insert-or-conflict above guarantees the row exists"
        return await self._to_domain(row)

    async def get_for_user(self, user_id: uuid.UUID) -> Cart | None:
        row = await self.session.scalar(
            select(CartModel).where(CartModel.user_id == user_id)
        )
        return await self._to_domain(row) if row is not None else None

    async def get_line_owner(self, line_id: uuid.UUID) -> Cart | None:
        line_row = await self.session.scalar(
            select(CartLineModel).where(CartLineModel.id == line_id)
        )
        if line_row is None:
            return None
        cart_row = await self.session.scalar(
            select(CartModel).where(CartModel.id == line_row.cart_id).with_for_update()
        )
        assert cart_row is not None, "cart_lines.cart_id is a NOT NULL foreign key"
        return await self._to_domain(cart_row)

    async def save(self, cart: Cart) -> None:
        existing_rows = {
            row.id: row
            for row in (
                await self.session.scalars(
                    select(CartLineModel).where(CartLineModel.cart_id == cart.id.value)
                )
            ).all()
        }
        domain_ids = {line.id for line in cart.lines}
        for row_id, row in existing_rows.items():
            if row_id not in domain_ids:
                await self.session.delete(row)

        for line in cart.lines:
            existing_row = existing_rows.get(line.id)
            if existing_row is None:
                self.session.add(_to_line_model(cart.id.value, line))
            else:
                existing_row.quantity = line.quantity

    async def _to_domain(self, row: CartModel) -> Cart:
        line_rows = list(
            (
                await self.session.scalars(
                    select(CartLineModel)
                    .where(CartLineModel.cart_id == row.id)
                    .order_by(CartLineModel.added_at.asc(), CartLineModel.id.asc())
                )
            ).all()
        )
        return Cart.reconstitute(
            CartId.create(row.id),
            user_id=row.user_id,
            lines=[
                CartLine(
                    id=line_row.id,
                    product_id=line_row.product_id,
                    quantity=line_row.quantity,
                    added_at=line_row.added_at,
                )
                for line_row in line_rows
            ],
            created_at=row.created_at,
        )


def _to_line_model(cart_id: uuid.UUID, line: CartLine) -> CartLineModel:
    return CartLineModel(
        id=line.id,
        cart_id=cart_id,
        product_id=line.product_id,
        quantity=line.quantity,
        added_at=line.added_at,
    )


# Статическая структурная проверка: mypy убеждается, что конкретная
# реализация удовлетворяет каждую операцию, требуемую доменным контрактом
# репозитория.
_cart_repository_implementation: type[CartRepositoryPort] = CartRepository
