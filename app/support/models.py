import enum
from datetime import datetime

from sqlalchemy import DateTime, ForeignKey, Index, String, Text, func
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.models import Base, User


class UserRole(enum.StrEnum):
    ADMIN = "admin"
    USER = "user"


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

    created_by_user_id: Mapped[int] = mapped_column(
        ForeignKey("users.id", ondelete="CASCADE"), index=True
    )
    subject: Mapped[str] = mapped_column(String(255))
    status: Mapped[SupportStatus] = mapped_column(index=True)

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

    user_last_read_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    admin_last_read_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))

    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now()
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), onupdate=func.now()
    )
    closed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))

    messages: Mapped[list["ConversationMessage"]] = relationship(
        back_populates="conversation",
        cascade="all, delete-orphan",
        order_by="ConversationMessage.created_at",
    )

    creator: Mapped["User"] = relationship(
        foreign_keys=[created_by_user_id],
        back_populates="created_conversations",
    )

    assignee: Mapped["User | None"] = relationship(
        foreign_keys=[assigned_admin_id],
        back_populates="assigned_conversations",
    )

    __table_args__ = (
        # Индекс для быстрой выборки админом своих открытых тикетов
        Index("ix_conv_status_admin", "status", "assigned_admin_id"),
    )


class ConversationMessage(Base):
    __tablename__ = "conversation_messages"

    id: Mapped[int] = mapped_column(primary_key=True)

    conversation_id: Mapped[int] = mapped_column(
        ForeignKey("conversations.id", ondelete="CASCADE"), index=True
    )

    sender_user_id: Mapped[int | None] = mapped_column(
        ForeignKey("users.id", ondelete="SET NULL"), index=True, nullable=True
    )
    sender_role: Mapped[SenderRole]

    message: Mapped[str] = mapped_column(Text)

    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now()
    )

    conversation: Mapped["Conversation"] = relationship(
        back_populates="messages",
    )

    sender: Mapped["User | None"] = relationship(
        back_populates="messages",
    )

    __table_args__ = (
        # Индекс для быстрой загрузки истории конкретного чата
        Index("ix_conv_messages_history", "conversation_id", "created_at"),
    )
