import uuid

from kernel_platform.outbox.models import Base
from sqlalchemy import BigInteger, Boolean
from sqlalchemy.dialects.postgresql import UUID, insert
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker
from sqlalchemy.orm import Mapped, mapped_column

from application.ports import OwnerSearchState


class SearchOwnerStateRow(Base):
    """Durable Owner Search State (issue #288), populated by
    `catalog-search-worker` from `user.registered/activated/deactivated/
    deleted.v1`. Deliberately separate from `owner_read_model`: that table
    defaults a missing owner to active (cold-start reconciliation, ADR 0011);
    this one must default a missing owner to inactive (deny-by-default) —
    opposite defaults can't share one table."""

    __tablename__ = "search_owner_state"

    user_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True)
    is_active: Mapped[bool] = mapped_column(Boolean)
    last_applied_outbox_id: Mapped[int] = mapped_column(BigInteger, default=0)


async def get_search_owner_state(
    session: AsyncSession, user_id: uuid.UUID
) -> SearchOwnerStateRow | None:
    return await session.get(SearchOwnerStateRow, user_id)


async def upsert_search_owner_state(
    session: AsyncSession,
    *,
    user_id: uuid.UUID,
    is_active: bool,
    last_applied_outbox_id: int,
    commit: bool = True,
) -> bool:
    """Versioned upsert (ADR 0011 pattern): applies only if
    `last_applied_outbox_id` strictly increases, guarding against both
    duplicate delivery (same id) and out-of-order delivery (an older id
    arriving after a newer one). Returns whether the row was actually
    written, so callers can skip a redundant OpenSearch mass-update."""
    stmt = insert(SearchOwnerStateRow).values(
        user_id=user_id,
        is_active=is_active,
        last_applied_outbox_id=last_applied_outbox_id,
    )
    upsert_stmt = stmt.on_conflict_do_update(
        index_elements=[SearchOwnerStateRow.user_id],
        set_={
            "is_active": stmt.excluded.is_active,
            "last_applied_outbox_id": stmt.excluded.last_applied_outbox_id,
        },
        where=(
            SearchOwnerStateRow.last_applied_outbox_id
            < stmt.excluded.last_applied_outbox_id
        ),
    ).returning(SearchOwnerStateRow.user_id)
    result = await session.execute(upsert_stmt)
    applied = result.scalar_one_or_none() is not None
    if commit:
        await session.commit()
    return applied


class SqlOwnerSearchStateStore:
    """Worker-scoped adapter for `OwnerSearchStateStore` — opens its own
    session per call (there is no per-request session in a standalone
    consumer process, unlike `SqlOwnerReadModel`)."""

    def __init__(self, session_factory: async_sessionmaker[AsyncSession]) -> None:
        self._session_factory = session_factory

    async def get(self, user_id: uuid.UUID) -> OwnerSearchState | None:
        async with self._session_factory() as session:
            row = await get_search_owner_state(session, user_id)
        if row is None:
            return None
        return OwnerSearchState(
            user_id=row.user_id,
            is_active=row.is_active,
            last_applied_outbox_id=row.last_applied_outbox_id,
        )

    async def upsert(self, state: OwnerSearchState) -> bool:
        async with self._session_factory() as session:
            async with session.begin():
                return await upsert_search_owner_state(
                    session,
                    user_id=state.user_id,
                    is_active=state.is_active,
                    last_applied_outbox_id=state.last_applied_outbox_id,
                    commit=False,
                )
