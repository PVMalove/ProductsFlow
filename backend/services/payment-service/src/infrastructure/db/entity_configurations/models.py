import uuid
from datetime import datetime

from kernel_platform.outbox.models import Base
from sqlalchemy import DateTime, Integer, Text, UniqueConstraint, func
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.orm import Mapped, mapped_column

# Общий `kernel_platform.outbox.models.Base` (issue #371, архитектурный бриф
# D1) — разворот issue #368's исходного решения (собственный, изолированный
# `Base`, оставленного явно открытым для #371/#374): payment-service теперь
# потребляет `payment.authorize.v1`/`payment.void.v1` и публикует
# коррелированные факты результата, поэтому его схема разделяет `Base` с
# `OutboxMessage`/`InboxMessage` — импорт `Base` из этого модуля исполняет
# весь его код, регистрируя обе модели на одном `Base.metadata` независимо от
# того, какие имена реально импортированы. Прямое зеркалирование
# inventory-service (issue #367/#370) — единственного реального прецедента
# в этой кодовой базе.


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
