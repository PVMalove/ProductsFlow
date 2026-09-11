import uuid

from kernel_platform.outbox.models import Base
from sqlalchemy import Integer
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.orm import Mapped, mapped_column

# Тот же `Base` (и, значит, `Base.metadata`), что и `kernel_platform`'овский
# `OutboxMessage` (ADR 0010) — так тесты (`Base.metadata.create_all`) и
# написанная вручную Alembic-ревизия видят все таблицы inventory-service
# вместе.


class InventoryModel(Base):
    """PK = `product_id` (ADR 0016, issue #367) — не отдельный синтетический
    id: один Inventory Pool на продукт закреплён уже на уровне схемы."""

    __tablename__ = "inventory"
    # `pending_audit_reason` ниже намеренно не использует `Mapped[...]` —
    # разрешаем declarative-сканеру SQLAlchemy 2.0 пропустить его как
    # немаппленный обычный Python-атрибут, а не колонку (см. пояснение там же).
    __allow_unmapped__ = True

    product_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True)
    quantity: Mapped[int] = mapped_column(Integer, default=0, server_default="0")

    # Транзитное поле, не колонка (`__allow_unmapped__` выше). Несёт `reason`
    # из запроса корректировки в audit before_update-listener в рамках
    # одного flush (issue #367) — сам `reason` не персистится в БД.
    pending_audit_reason: str | None = None
