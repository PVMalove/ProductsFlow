import enum
from datetime import datetime

from sqlalchemy import DateTime, ForeignKey, String, func
from sqlalchemy.orm import Mapped, mapped_column

from app.models import Base


class SupportStatus(enum.StrEnum):
    NEW = "new"
    IN_PROGRESS = "in_progress"
    CLOSED = "closed"


class SenderRole(enum.StrEnum):
    USER = "user"
    ADMIN = "admin"


class Conversation(Base):
    __tablename__ = "conversations"

    id: Mapped[int] = mapped_column(primary_key=True)

    # Если юзер удален - удаляем и его тикеты (CASCADE).
    created_by_user_id: Mapped[int] = mapped_column(
        ForeignKey("users.id", ondelete="CASCADE"), index=True
    )

    subject: Mapped[str] = mapped_column(String(255))

    status: Mapped[SupportStatus] = mapped_column(index=True)

    # Если админ уволился/удален, тикет не должен исчезнуть — сбрасываем в NULL
    assigned_admin_id: Mapped[int | None] = mapped_column(
        ForeignKey("users.id", ondelete="SET NULL"),
        index=True,
    )

    first_admin_reply_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True)
    )

    last_message_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), index=True
    )
    last_message_by_role: Mapped[SenderRole]

    # Симметрия статусов прочтения
    user_last_read_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    admin_last_read_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))

    # Аудит
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now()
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), onupdate=func.now()
    )
    closed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
