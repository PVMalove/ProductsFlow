import uuid

from kernel_domain.domain_event import DomainEvent
from kernel_domain.result import Result
from kernel_platform.outbox.models import OutboxMessage
from sqlalchemy import Select, select, text, tuple_
from sqlalchemy.ext.asyncio import AsyncSession

from catalog.domain.events import (
    ProductActivated,
    ProductCreated,
    ProductDeactivated,
    ProductDeleted,
    ProductUpdated,
)
from catalog.domain.product import Product
from catalog.domain.product_id import ProductId
from catalog.infrastructure.db.models import ProductModel
from catalog.infrastructure.db.pagination import (
    Cursor,
    PageInfo,
    ProductPage,
    encode_cursor,
)

_NEXT_PRODUCT_ID = text("SELECT nextval(pg_get_serial_sequence('products', 'id'))")

# Алиас, а не `list[ProductModel]` напрямую в аннотациях `ProductRepository`:
# метод `list` (AC issue #148) одноимённый с builtin'ом внутри той же
# области видимости класса — mypy резолвит голый `list[...]` в аннотациях
# методов этого класса в сам метод, а не в builtin (известная особенность
# self-referencing имён в теле класса).
_ProductRows = list[ProductModel]


def _to_domain(row: ProductModel) -> Product:
    return Product(
        ProductId(row.id),
        name=row.name,
        description=row.description,
        price=row.price,
        category=row.category,
        user_id=row.user_id,
        is_active=row.is_active,
    )


def _to_outbox_message(event: DomainEvent) -> OutboxMessage:
    if isinstance(event, ProductCreated):
        event_type = "product.created.v1"
        payload = {
            "product_id": event.product_id.value,
            "user_id": str(event.user_id),
            "name": event.name,
            "category": event.category,
            "price": event.price,
        }
        product_id = event.product_id
    elif isinstance(event, ProductUpdated):
        event_type = "product.updated.v1"
        payload = {"product_id": event.product_id.value}
        product_id = event.product_id
    elif isinstance(event, ProductActivated):
        event_type = "product.activated.v1"
        payload = {"product_id": event.product_id.value}
        product_id = event.product_id
    elif isinstance(event, ProductDeactivated):
        event_type = "product.deactivated.v1"
        payload = {"product_id": event.product_id.value}
        product_id = event.product_id
    elif isinstance(event, ProductDeleted):
        event_type = "product.deleted.v1"
        payload = {"product_id": event.product_id.value}
        product_id = event.product_id
    else:  # pragma: no cover — защита от забытого будущего типа события
        raise TypeError(f"Неизвестное доменное событие Product: {type(event)!r}")

    return OutboxMessage(
        aggregate_type="Product",
        aggregate_id=product_id.value,
        event_type=event_type,
        payload=payload,
        occurred_at=event.occurred_on_utc,
    )


class ProductRepository:
    """CRUD + keyset-пагинация для `Product` (issue #148). `_drain_outbox` —
    единственное место, которое видит и доменную сущность, и `AsyncSession`
    (ADR 0021): каждый мутирующий метод сам коммитит свою транзакцию, атомарно
    фиксируя изменение `ProductModel` и вставленные строки `outbox_messages`.
    """

    def __init__(self, session: AsyncSession) -> None:
        self.session = session

    async def create(
        self,
        *,
        name: str,
        description: str,
        price: float,
        category: str,
        user_id: uuid.UUID,
    ) -> Result[Product]:
        next_id = await self.session.scalar(_NEXT_PRODUCT_ID)
        assert next_id is not None
        result = Product.create(
            ProductId(next_id),
            name=name,
            description=description,
            price=price,
            category=category,
            user_id=user_id,
        )
        if result.is_err:
            return result

        product = result.value
        self.session.add(
            ProductModel(
                id=product.id.value,
                name=product.name,
                description=product.description,
                price=product.price,
                category=product.category,
                user_id=product.user_id,
                is_active=product.is_active,
            )
        )
        await self._drain_outbox(product)
        await self.session.commit()
        return result

    async def get_by_id(self, product_id: ProductId) -> Product | None:
        row = await self.session.get(ProductModel, product_id.value)
        return _to_domain(row) if row is not None else None

    async def update(
        self,
        product_id: ProductId,
        *,
        name: str | None = None,
        description: str | None = None,
        price: float | None = None,
        category: str | None = None,
    ) -> Result[Product] | None:
        row = await self.session.get(ProductModel, product_id.value)
        if row is None:
            return None

        product = _to_domain(row)
        result = product.update(
            name=name, description=description, price=price, category=category
        )
        if result.is_err:
            return Result.fail(result.error)

        row.name = product.name
        row.description = product.description
        row.price = product.price
        row.category = product.category
        await self._drain_outbox(product)
        await self.session.commit()
        return Result.ok(product)

    async def activate(self, product_id: ProductId) -> Result[Product] | None:
        return await self._toggle_active(product_id, activate=True)

    async def deactivate(self, product_id: ProductId) -> Result[Product] | None:
        return await self._toggle_active(product_id, activate=False)

    async def _toggle_active(
        self, product_id: ProductId, *, activate: bool
    ) -> Result[Product] | None:
        row = await self.session.get(ProductModel, product_id.value)
        if row is None:
            return None

        product = _to_domain(row)
        result = product.activate() if activate else product.deactivate()
        if result.is_err:
            return Result.fail(result.error)

        row.is_active = product.is_active
        await self._drain_outbox(product)
        await self.session.commit()
        return Result.ok(product)

    async def delete(self, product_id: ProductId) -> Product | None:
        row = await self.session.get(ProductModel, product_id.value)
        if row is None:
            return None

        product = _to_domain(row)
        product.mark_deleted()
        await self._drain_outbox(product)
        await self.session.delete(row)
        await self.session.commit()
        return product

    async def list(
        self,
        *,
        limit: int,
        after: Cursor | None = None,
        before: Cursor | None = None,
    ) -> ProductPage:
        base_stmt = select(ProductModel)
        if before is not None:
            stmt = base_stmt.where(
                tuple_(ProductModel.created_at, ProductModel.id)
                > (before.created_at, before.id)
            ).order_by(ProductModel.created_at.asc(), ProductModel.id.asc())
            page, has_prev = await self._overfetch(stmt, limit)
            page.reverse()
            has_more = True
        else:
            stmt = base_stmt
            if after is not None:
                stmt = stmt.where(
                    tuple_(ProductModel.created_at, ProductModel.id)
                    < (after.created_at, after.id)
                )
            stmt = stmt.order_by(ProductModel.created_at.desc(), ProductModel.id.desc())
            page, has_more = await self._overfetch(stmt, limit)
            has_prev = after is not None

        if not page:
            return ProductPage(
                items=[],
                page_info=PageInfo(
                    next_cursor=None, prev_cursor=None, has_more=False, has_prev=False
                ),
            )

        return ProductPage(
            items=[_to_domain(row) for row in page],
            page_info=PageInfo(
                next_cursor=(
                    encode_cursor(page[-1].created_at, page[-1].id)
                    if has_more
                    else None
                ),
                prev_cursor=(
                    encode_cursor(page[0].created_at, page[0].id) if has_prev else None
                ),
                has_more=has_more,
                has_prev=has_prev,
            ),
        )

    async def _overfetch(
        self, stmt: Select[tuple[ProductModel]], limit: int
    ) -> tuple[_ProductRows, bool]:
        rows: _ProductRows = list(
            (await self.session.scalars(stmt.limit(limit + 1))).all()
        )
        return rows[:limit], len(rows) > limit

    async def _drain_outbox(self, product: Product) -> None:
        for event in product.pull_events():
            self.session.add(_to_outbox_message(event))
