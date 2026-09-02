import uuid
from datetime import datetime
from math import ceil

from kernel_platform.outbox.models import Base
from observability.context import actor_id_var
from sqlalchemy import (
    BigInteger,
    DateTime,
    ForeignKey,
    Identity,
    Text,
    event,
    func,
    insert,
    inspect,
    select,
)
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.engine import Connection
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import Mapped, Mapper, mapped_column

from application.ports import (
    UserAuditAction,
    UserAuditEntry,
    UserAuditPage,
    UserAuditQueryPort,
)
from domain.user_id import UserId
from infrastructure.db.models import UserModel


class UserAuditLog(Base):
    """Неизменяемая история мутаций User с FK на строку пользователя."""

    __tablename__ = "user_audit_logs"

    id: Mapped[int] = mapped_column(BigInteger, Identity(), primary_key=True)
    user_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("users.id")
    )
    actor_user_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("users.id")
    )
    action: Mapped[UserAuditAction] = mapped_column(Text)
    description: Mapped[str] = mapped_column(Text, default="", server_default="")
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now()
    )


def _actor_for_audit(user_id: uuid.UUID) -> uuid.UUID:
    actor = actor_id_var.get()
    return user_id if actor is None else uuid.UUID(str(actor))


def _write_audit(
    connection: Connection,
    *,
    user_id: uuid.UUID,
    action: UserAuditAction,
    description: str,
) -> None:
    connection.execute(
        insert(UserAuditLog).values(
            user_id=user_id,
            actor_user_id=_actor_for_audit(user_id),
            action=action,
            description=description,
        )
    )


@event.listens_for(UserModel, "after_insert")
def _on_user_insert(
    _mapper: Mapper[UserModel], connection: Connection, target: UserModel
) -> None:
    _write_audit(
        connection,
        user_id=target.id,
        action=UserAuditAction.REGISTERED,
        description=f"Зарегистрирован пользователь {target.email!r}",
    )


@event.listens_for(UserModel, "before_update")
def _on_user_update(
    _mapper: Mapper[UserModel], connection: Connection, target: UserModel
) -> None:
    state = inspect(target)
    if state.attrs.password_hash.history.has_changes():
        _write_audit(
            connection,
            user_id=target.id,
            action=UserAuditAction.PASSWORD_CHANGED,
            description="Изменён пароль пользователя",
        )
    if state.attrs.is_active.history.has_changes():
        active = target.is_active
        _write_audit(
            connection,
            user_id=target.id,
            action=(
                UserAuditAction.ACTIVATED if active else UserAuditAction.DEACTIVATED
            ),
            description=(
                "Пользователь активирован" if active else "Пользователь деактивирован"
            ),
        )


async def get_audit_logs_by_user(
    session: AsyncSession, user_id: uuid.UUID
) -> list[UserAuditLog]:
    rows = await session.scalars(
        select(UserAuditLog)
        .where(UserAuditLog.user_id == user_id)
        .order_by(UserAuditLog.created_at.asc(), UserAuditLog.id.asc())
    )
    return list(rows.all())


def _to_entry(row: UserAuditLog) -> UserAuditEntry:
    return UserAuditEntry(
        id=row.id,
        user_id=UserId(row.user_id),
        actor_user_id=UserId(row.actor_user_id),
        action=UserAuditAction(str(row.action)),
        description=row.description,
        created_at=row.created_at,
    )


class SqlUserAuditReader:
    """SQL adapter for global and personal User audit reads."""

    def __init__(self, session: AsyncSession) -> None:
        self._session = session

    async def get_by_user(self, user_id: UserId) -> list[UserAuditEntry]:
        rows = await get_audit_logs_by_user(self._session, user_id.value)
        return [_to_entry(row) for row in rows]

    async def list_all(self, *, page_index: int, page_size: int) -> UserAuditPage:
        total = int(
            await self._session.scalar(select(func.count()).select_from(UserAuditLog))
            or 0
        )
        rows = await self._session.scalars(
            select(UserAuditLog)
            .order_by(UserAuditLog.created_at.desc(), UserAuditLog.id.desc())
            .offset((page_index - 1) * page_size)
            .limit(page_size)
        )
        return UserAuditPage(
            items=[_to_entry(row) for row in rows.all()],
            page_index=page_index,
            page_size=page_size,
            total=total,
            total_pages=ceil(total / page_size) if total else 0,
        )


_user_audit_query_port_implementation: type[UserAuditQueryPort] = SqlUserAuditReader
