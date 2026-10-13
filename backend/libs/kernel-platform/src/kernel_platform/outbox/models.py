# ruff: noqa: E501
import uuid
from datetime import datetime
from typing import Any

from sqlalchemy import BigInteger, DateTime, Index, Text, func, text
from sqlalchemy.dialects.postgresql import JSONB, UUID
from sqlalchemy.orm import DeclarativeBase, Mapped, mapped_column


class Base(DeclarativeBase):
    pass


class OutboxMessage(Base):
    """Transactional Outbox : строка, вставленная в одной транзакции
    с доменной мутацией, доезжает до RabbitMQ через `OutboxPublisher`.
    """

    __tablename__ = "outbox_messages"
    __table_args__ = (
        Index(
            "ix_outbox_messages_unpublished",
            "id",
            postgresql_where=text("published_at IS NULL"),
        ),
    )

    id: Mapped[int] = mapped_column(BigInteger, primary_key=True)
    aggregate_type: Mapped[str] = mapped_column(Text)
    aggregate_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True))
    event_type: Mapped[str] = mapped_column(Text)
    payload: Mapped[dict[str, Any]] = mapped_column(JSONB)
    occurred_at: Mapped[datetime] = mapped_column(DateTime(timezone=True))
    published_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    attempts: Mapped[int] = mapped_column(default=0, server_default="0")
    next_attempt_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    trace_context: Mapped[str | None] = mapped_column(Text)


class InboxMessage(Base):
    """A command claimed by its owner before its local effect is applied.

    ``command_id`` is globally unique, so a broker redelivery can safely be
    ACKed after the original transaction has committed.  The command handler
    writes its business state and any ``OutboxMessage`` through the same
    session and transaction that creates this row.
    """

    __tablename__ = "inbox_messages"

    command_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True)
    command_type: Mapped[str] = mapped_column(Text)
    causation_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True))
    correlation_id: Mapped[str] = mapped_column(Text)
    trace_context: Mapped[str | None] = mapped_column(Text)
    processed_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now()
    )
