import uuid

from kernel_platform.outbox.models import Base
from sqlalchemy import BigInteger, Boolean, Text
from sqlalchemy.dialects.postgresql import UUID, insert
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import Mapped, mapped_column

from application.ports import UserProjectionPort, UserProjectionSnapshot

# Cold-start сентинел (зеркалит catalog's `owner_read_model`, ADR 0011):
# реальные события несут `outbox_messages.id >= 1` (bigserial), поэтому
# строка, засеянная версией 0, всегда проигрывает первому же настоящему
# событию.
COLD_START_SENTINEL_VERSION = 0


class UserProjectionRow(Base):
    """Локальная event-driven копия identity User в support (ADR 0012).

    Deny-by-default: отсутствующая строка означает `401 UNAUTHENTICATED`,
    а `deleted`/`is_active` определяют `403 FORBIDDEN`. `deleted` — это
    tombstone, не удаление — в сочетании с guard'ом версии
    `last_applied_outbox_id` устаревшее или повторно доставленное событие
    identity никогда не может воскресить удалённого пользователя."""

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
    """Один атомарный upsert, версионированный по `last_applied_outbox_id`
    (ADR 0012) — не read-then-write: событийный консьюмер и любой будущий
    cold-fetch не создают гонку между собой. События активации/деактивации
    identity несут только изменённое поле, поэтому `None` здесь сохраняет
    значение существующей строки при конфликте."""
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
    """SQL-адаптер для application-порта `UserProjectionPort`."""

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
