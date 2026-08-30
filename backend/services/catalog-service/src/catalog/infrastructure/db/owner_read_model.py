import uuid

from kernel_platform.outbox.models import Base
from sqlalchemy import BigInteger, Boolean, Text
from sqlalchemy.dialects.postgresql import UUID, insert
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import Mapped, mapped_column

from catalog.infrastructure.identity_gateway import IdentityGateway

# Сентинел синхронного добора (ADR 0012/0019): реальные события несут
# `outbox_messages.id >= 1` (bigserial), поэтому строка с версией 0 всегда
# проигрывает первому же настоящему событию.
COLD_START_SENTINEL_VERSION = 0


class OwnerReadModelRow(Base):
    """Локальная read-модель Владельца в catalog (issue #148 миграция,
    issue #149 — первый писатель/читатель): наполняется событиями
    `user.*.v1` консьюмером (issue #151, ещё не реализован) и синхронным
    добором на холодном промахе (ADR 0012/0019)."""

    __tablename__ = "owner_read_model"

    user_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True)
    role: Mapped[str] = mapped_column(Text)
    is_active: Mapped[bool] = mapped_column(Boolean)
    last_applied_outbox_id: Mapped[int] = mapped_column(BigInteger, default=0)


async def get_owner_read_model(
    session: AsyncSession, user_id: uuid.UUID
) -> OwnerReadModelRow | None:
    return await session.get(OwnerReadModelRow, user_id)


async def upsert_owner_read_model(
    session: AsyncSession,
    *,
    user_id: uuid.UUID,
    role: str,
    is_active: bool,
    last_applied_outbox_id: int,
) -> None:
    """Один атомарный upsert, версионированный по `last_applied_outbox_id`
    (ADR 0019) — не read-then-write: конкурентные писатели (событийный
    консьюмер и синхронный добор) не открывают окно гонки между ними."""
    stmt = insert(OwnerReadModelRow).values(
        user_id=user_id,
        role=role,
        is_active=is_active,
        last_applied_outbox_id=last_applied_outbox_id,
    )
    stmt = stmt.on_conflict_do_update(
        index_elements=[OwnerReadModelRow.user_id],
        set_={
            "role": stmt.excluded.role,
            "is_active": stmt.excluded.is_active,
            "last_applied_outbox_id": stmt.excluded.last_applied_outbox_id,
        },
        where=(
            OwnerReadModelRow.last_applied_outbox_id
            < stmt.excluded.last_applied_outbox_id
        ),
    )
    await session.execute(stmt)
    await session.commit()


async def ensure_owner_read_model_seeded(
    session: AsyncSession,
    identity: IdentityGateway,
    *,
    user_id: uuid.UUID,
    token: str,
) -> None:
    """Синхронный добор на холодном промахе (ADR 0012/0019, user story 15):
    вызывается только с токеном самого `user_id` (`GET /api/v1/users/me`
    отдаёт информацию только о предъявителе токена) — на создании Товара,
    прежде чем видимость этого Товара станет вопросом для других
    Наблюдателей. Не трогает уже существующую строку — она либо свежее
    (событие уже применилось), либо будет перезаписана тем же событием
    позже, upsert-условие (ADR 0019) само решит, что важнее."""
    if await get_owner_read_model(session, user_id) is not None:
        return
    info = await identity.fetch_current_user(token)
    await upsert_owner_read_model(
        session,
        user_id=info.id,
        role=info.role,
        is_active=info.is_active,
        last_applied_outbox_id=COLD_START_SENTINEL_VERSION,
    )
