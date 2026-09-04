import uuid
from datetime import datetime

from kernel_platform.outbox.models import Base
from sqlalchemy import (
    BigInteger,
    CheckConstraint,
    DateTime,
    ForeignKey,
    Index,
    String,
    Text,
    func,
)
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.orm import Mapped, mapped_column


class TicketModel(Base):
    __tablename__ = "tickets"
    __table_args__ = (
        Index("ix_tickets_author_created_at_id", "author_id", "created_at", "id"),
        CheckConstraint(
            "length(btrim(subject)) BETWEEN 1 AND 200", name="ck_tickets_subject_length"
        ),
        CheckConstraint(
            "status IN ('OPEN', 'IN_PROGRESS', 'RESOLVED', 'CLOSED')",
            name="ck_tickets_status",
        ),
    )

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True)
    author_id: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True), nullable=True
    )
    subject: Mapped[str] = mapped_column(String(200), nullable=False)
    status: Mapped[str] = mapped_column(
        String(32), nullable=False, server_default="OPEN"
    )
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default=func.now()
    )


class TicketMessageModel(Base):
    __tablename__ = "ticket_messages"
    __table_args__ = (
        Index(
            "ix_ticket_messages_ticket_created_at_id", "ticket_id", "created_at", "id"
        ),
        CheckConstraint(
            "length(btrim(body)) BETWEEN 1 AND 10000",
            name="ck_ticket_messages_body_length",
        ),
    )

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True)
    ticket_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("tickets.id", ondelete="CASCADE"), nullable=False
    )
    author_id: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True), nullable=True
    )
    body: Mapped[str] = mapped_column(Text, nullable=False)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default=func.now()
    )
    is_system: Mapped[bool] = mapped_column(
        nullable=False, default=False, server_default="false"
    )
    is_deleted: Mapped[bool] = mapped_column(
        nullable=False, default=False, server_default="false"
    )


class ProcessedMessage(Base):
    """Inbox-квитанция для события identity, идентифицированного его outbox id."""

    __tablename__ = "processed_messages"

    message_id: Mapped[int] = mapped_column(BigInteger, primary_key=True)
    processed_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default=func.now()
    )
