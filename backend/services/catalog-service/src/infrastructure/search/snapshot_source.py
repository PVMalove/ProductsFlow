"""PostgreSQL source of record for search bootstrap and reconciliation."""

import uuid
from collections.abc import AsyncIterator

from sqlalchemy import select
from sqlalchemy.engine import Row
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from application.ports import SearchSnapshotWithOwner
from application.search_snapshot import ProductSearchSnapshot
from infrastructure.db.entity_configurations.models import ProductModel
from infrastructure.db.search_owner_state import SearchOwnerStateRow


class PostgresProductSearchSnapshotSource:
    """Reads stable keyset batches; no RabbitMQ replay is required."""

    def __init__(self, session_factory: async_sessionmaker[AsyncSession]) -> None:
        self._session_factory = session_factory

    async def get(self, product_id: uuid.UUID) -> SearchSnapshotWithOwner | None:
        async with self._session_factory() as session:
            row = (
                await session.execute(
                    select(ProductModel, SearchOwnerStateRow.is_active)
                    .outerjoin(
                        SearchOwnerStateRow,
                        SearchOwnerStateRow.user_id == ProductModel.user_id,
                    )
                    .where(ProductModel.id == product_id)
                )
            ).one_or_none()
        return self._to_snapshot(row) if row is not None else None

    async def stream_batches(
        self, *, batch_size: int
    ) -> AsyncIterator[list[SearchSnapshotWithOwner]]:
        after_id: uuid.UUID | None = None
        while True:
            async with self._session_factory() as session:
                statement = (
                    select(ProductModel, SearchOwnerStateRow.is_active)
                    .outerjoin(
                        SearchOwnerStateRow,
                        SearchOwnerStateRow.user_id == ProductModel.user_id,
                    )
                    .order_by(ProductModel.id)
                    .limit(batch_size)
                )
                if after_id is not None:
                    statement = statement.where(ProductModel.id > after_id)
                rows = list((await session.execute(statement)).all())
            if not rows:
                return
            yield [self._to_snapshot(row) for row in rows]
            after_id = rows[-1][0].id

    @staticmethod
    def _to_snapshot(
        row: Row[tuple[ProductModel, bool]],
    ) -> SearchSnapshotWithOwner:
        product, owner_is_active = row
        return SearchSnapshotWithOwner(
            snapshot=ProductSearchSnapshot(
                product_id=product.id,
                user_id=product.user_id,
                name=product.name,
                description=product.description,
                category=product.category,
                price=product.price,
                is_active=product.is_active,
                search_revision=product.search_revision,
                created_at=product.created_at,
            ),
            owner_is_active=owner_is_active is True,
        )
