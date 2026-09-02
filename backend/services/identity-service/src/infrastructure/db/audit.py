import enum
import uuid
from datetime import datetime

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
)
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.engine import Connection
from sqlalchemy.orm import Mapped, Mapper, mapped_column

from infrastructure.db.models import UserModel


class UserAuditAction(enum.StrEnum):
    REGISTERED = "registered"
    PASSWORD_CHANGED = "password_changed"
    ACTIVATED = "activated"
    DEACTIVATED = "deactivated"


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
