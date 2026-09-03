import uuid

from kernel_platform.outbox.models import Base
from sqlalchemy import BigInteger, Boolean, Text
from sqlalchemy.dialects.postgresql import UUID, insert
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import Mapped, mapped_column

from application.ports import UserProjectionPort, UserProjectionSnapshot

# Cold-start sentinel (mirrors catalog's `owner_read_model`, ADR 0019): real
# events carry `outbox_messages.id >= 1` (bigserial), so a row seeded at
# version 0 always loses to the first genuine event.
COLD_START_SENTINEL_VERSION = 0


class UserProjectionRow(Base):
    """Support's local, event-driven copy of an identity User (ADR 0033).

    Deny-by-default: a missing row means `401 UNAUTHENTICATED`, while
    `deleted`/`is_active` drive `403 FORBIDDEN`. `deleted` is a tombstone, not
    a delete — combined with the `last_applied_outbox_id` version guard, a
    stale or replayed identity event can never revive a deleted user."""

    __tablename__ = "user_projection"

    user_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True)
    role: Mapped[str] = mapped_column(Text)
    is_active: Mapped[bool] = mapped_column(Boolean)
    deleted: Mapped[bool] = mapped_column(Boolean, default=False)
    last_applied_outbox_id: Mapped[int] = mapped_column(BigInteger, default=0)


async def get_user_projection(
    session: AsyncSession, user_id: uuid.UUID
) -> UserProjectionRow | None:
    return await session.get(UserProjectionRow, user_id)


async def upsert_user_projection(
    session: AsyncSession,
    *,
    user_id: uuid.UUID,
    role: str | None,
    is_active: bool | None,
    deleted: bool | None,
    last_applied_outbox_id: int,
    commit: bool = True,
) -> None:
    """One atomic, `last_applied_outbox_id`-versioned upsert (ADR 0019/0033) —
    not read-then-write: the event consumer and any future cold-fetch cannot
    race each other. Identity's activation/deactivation events carry only the
    changed field, so a `None` here preserves the existing row's value on
    conflict."""
    insert_role = role if role is not None else "user"
    insert_is_active = is_active if is_active is not None else True
    insert_deleted = deleted if deleted is not None else False
    stmt = insert(UserProjectionRow).values(
        user_id=user_id,
        role=insert_role,
        is_active=insert_is_active,
        deleted=insert_deleted,
        last_applied_outbox_id=last_applied_outbox_id,
    )
    stmt = stmt.on_conflict_do_update(
        index_elements=[UserProjectionRow.user_id],
        set_={
            "role": (
                stmt.excluded.role if role is not None else UserProjectionRow.role
            ),
            "is_active": (
                stmt.excluded.is_active
                if is_active is not None
                else UserProjectionRow.is_active
            ),
            "deleted": (
                stmt.excluded.deleted
                if deleted is not None
                else UserProjectionRow.deleted
            ),
            "last_applied_outbox_id": stmt.excluded.last_applied_outbox_id,
        },
        where=(
            UserProjectionRow.last_applied_outbox_id
            < stmt.excluded.last_applied_outbox_id
        ),
    )
    await session.execute(stmt)
    if commit:
        await session.commit()


class SqlUserProjection:
    """SQL adapter for the application `UserProjectionPort`."""

    def __init__(self, session: AsyncSession) -> None:
        self._session = session

    async def get(self, user_id: uuid.UUID) -> UserProjectionSnapshot | None:
        row = await get_user_projection(self._session, user_id)
        if row is None:
            return None
        return UserProjectionSnapshot(
            user_id=row.user_id,
            role=row.role,
            is_active=row.is_active,
            deleted=row.deleted,
            last_applied_outbox_id=row.last_applied_outbox_id,
        )


_user_projection_port_implementation: type[UserProjectionPort] = SqlUserProjection
