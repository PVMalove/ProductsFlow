from datetime import UTC, datetime

from kernel_platform.outbox.models import Base
from sqlalchemy import BigInteger, DateTime, func
from sqlalchemy.orm import Mapped, mapped_column


class ProcessedMessage(Base):
    """Inbox-таблица, используемая воркером catalog для at-least-once доставки."""

    __tablename__ = "processed_messages"

    message_id: Mapped[int] = mapped_column(BigInteger, primary_key=True)
    processed_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        server_default=func.now(),
        default=lambda: datetime.now(UTC),
    )
