import uuid

from kernel_domain.domain_event import DomainEvent
from kernel_domain.result import Result
from kernel_platform.outbox.models import OutboxMessage
from sqlalchemy import Select, select, text, tuple_
from sqlalchemy.ext.asyncio import AsyncSession

from domain.events import (
    ProductActivated,
    ProductCreated,
    ProductDeactivated,
    ProductDeleted,
    ProductEvent,
    ProductUpdated,
)
from domain.product import Product
from domain.product_id import ProductId
from domain.repositories import (
    Cursor,
    PageInfo,
    ProductPage,
)
from domain.repositories import (
    ProductRepository as ProductRepositoryPort,
)
from infrastructure.db.models import ProductModel
from infrastructure.db.owner_read_model import OwnerReadModelRow
from infrastructure.db.pagination import encode_cursor

_NEXT_PRODUCT_ID = text("SELECT nextval(pg_get_serial_sequence('products', 'id'))")

# Алиас, а не `list[ProductModel]` напрямую в аннотациях адаптера:
# метод `list` (AC issue #148) одноимённый с builtin'ом внутри той же
# области видимости класса — mypy резолвит голый `list[...]` в аннотациях
# методов этого класса в сам метод, а не в builtin (известная особенность
# self-referencing имён в теле класса).
_ProductRows = list[ProductModel]

_EVENT_TYPES: dict[type[ProductEvent], str] = {
    ProductCreated: "product.created.v1",
    ProductUpdated: "product.updated.v1",
    ProductActivated: "product.activated.v1",
    ProductDeactivated: "product.deactivated.v1",
    ProductDeleted: "product.deleted.v1",
}


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
    # Все домeнные события Product наследуют ProductEvent (product_id) —
    # `pull_events()` типизирован общим `DomainEvent` на уровне kernel-domain
    # (Entity не параметризуется по типу события), поэтому здесь нужен явный
    # guard для сужения типа.
    assert isinstance(event, ProductEvent)
    payload: dict[str, object] = {"product_id": event.product_id.value}
    if isinstance(event, ProductCreated):
        payload.update(
            user_id=str(event.user_id),
            name=event.name,
            category=event.category,
            price=event.price,
        )

    return OutboxMessage(
        aggregate_type="Product",
        aggregate_id=event.product_id.value,
        event_type=_EVENT_TYPES[type(event)],
        payload=payload,
        occurred_at=event.occurred_on_utc,
    )


class ProductRepository:
    """CRUD + keyset-пагинация для `Product` (issue #148). `_commit` —
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
        await self._commit(product)
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
        loaded = await self._load(product_id)
        if loaded is None:
            return None
        row, product = loaded

        result = product.update(
            name=name, description=description, price=price, category=category
        )
        if result.is_err:
            return Result.fail(result.error)

        row.name = product.name
        row.description = product.description
        row.price = product.price
        row.category = product.category
        await self._commit(product)
        return Result.ok(product)

    async def activate(self, product_id: ProductId) -> Result[Product] | None:
        return await self._toggle_active(product_id, activate=True)

    async def deactivate(self, product_id: ProductId) -> Result[Product] | None:
        return await self._toggle_active(product_id, activate=False)

    async def _toggle_active(
        self, product_id: ProductId, *, activate: bool
    ) -> Result[Product] | None:
        loaded = await self._load(product_id)
        if loaded is None:
            return None
        row, product = loaded

        result = product.activate() if activate else product.deactivate()
        if result.is_err:
            return Result.fail(result.error)

        row.is_active = product.is_active
        await self._commit(product)
        return Result.ok(product)

    async def delete(self, product_id: ProductId) -> Product | None:
        loaded = await self._load(product_id)
        if loaded is None:
            return None
        row, product = loaded

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
        # Списки не персонализированы и не имеют admin-обхода (ADR 0002/0003)
        # — деактивированный Товар и Товар деактивированного (или ещё не
        # добранного, issue #149) Владельца одинаково скрыты из выдачи для
        # всех, включая самого Владельца. INNER JOIN: Товар, чей Владелец ещё
        # не появился в owner_read_model (ни событием, ни синхронным
        # добором), из списков тоже не виден — тот же осторожный дефолт, что
        # и на прямом обращении по id.
        base_stmt = (
            select(ProductModel)
            .join(OwnerReadModelRow, OwnerReadModelRow.user_id == ProductModel.user_id)
            .where(
                ProductModel.is_active.is_(True), OwnerReadModelRow.is_active.is_(True)
            )
        )
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

    async def _load(self, product_id: ProductId) -> tuple[ProductModel, Product] | None:
        row = await self.session.get(ProductModel, product_id.value)
        if row is None:
            return None
        return row, _to_domain(row)

    async def _overfetch(
        self, stmt: Select[tuple[ProductModel]], limit: int
    ) -> tuple[_ProductRows, bool]:
        rows: _ProductRows = list(
            (await self.session.scalars(stmt.limit(limit + 1))).all()
        )
        return rows[:limit], len(rows) > limit

    async def _commit(self, product: Product) -> None:
        await self._drain_outbox(product)
        await self.session.commit()

    async def _drain_outbox(self, product: Product) -> None:
        for event in product.pull_events():
            self.session.add(_to_outbox_message(event))


# Static structural check: mypy verifies that the concrete implementation
# satisfies every operation required by the domain repository contract.
_product_repository_implementation: type[ProductRepositoryPort] = ProductRepository
