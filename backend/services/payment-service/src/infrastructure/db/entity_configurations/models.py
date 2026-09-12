import uuid
from datetime import datetime

from sqlalchemy import DateTime, Integer, Text, UniqueConstraint, func
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.orm import DeclarativeBase, Mapped, mapped_column

# Собственный `Base`, НЕ общий `kernel_platform.outbox.models.Base` (issue #368,
# архитектурный бриф D1): payment-service не публикует и не потребляет
# сообщения в этом тикете, поэтому его схема не должна тянуть за собой
# `outbox_messages`/`inbox_messages` — импорт общего `Base` регистрировал бы
# их на этом же `Base.metadata` безусловно, что прямо противоречит брифу
# («без processed_messages/outbox_messages/audit-таблиц»). RabbitMQ-обвязка
# (#371/#374) при появлении сможет либо завести здесь собственный
# outbox/inbox, либо повторно рассмотреть этот выбор.


class Base(DeclarativeBase):
    pass


class PaymentAuthorizationModel(Base):
    """PK = свежий `uuid.uuid4()` (ADR 0006, issue #368) — не сам
    idempotency-ключ. Три отдельные unique-колонки-ключа на одном агрегате
    (архитектурный бриф D3): authorize/void/capture каждый со своим
    idempotency-ключом жизненного цикла одной авторизации."""

    __tablename__ = "payment_authorizations"
    __table_args__ = (
        UniqueConstraint(
            "idempotency_key", name="uq_payment_authorizations_idempotency_key"
        ),
        UniqueConstraint(
            "void_idempotency_key",
            name="uq_payment_authorizations_void_idempotency_key",
        ),
        UniqueConstraint(
            "capture_idempotency_key",
            name="uq_payment_authorizations_capture_idempotency_key",
        ),
    )

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True)
    idempotency_key: Mapped[str] = mapped_column(Text, nullable=False)
    amount: Mapped[int] = mapped_column(Integer, nullable=False)
    payment_method_token: Mapped[str] = mapped_column(Text, nullable=False)
    status: Mapped[str] = mapped_column(Text, nullable=False)
    void_idempotency_key: Mapped[str | None] = mapped_column(Text, nullable=True)
    capture_idempotency_key: Mapped[str | None] = mapped_column(Text, nullable=True)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default=func.now()
    )
