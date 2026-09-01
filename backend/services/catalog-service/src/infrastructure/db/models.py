import uuid
from datetime import datetime

from kernel_platform.outbox.models import Base
from sqlalchemy import BigInteger, Identity, Index, String, Text, func
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.orm import Mapped, mapped_column

# Тот же `Base` (и, значит, `Base.metadata`), что и `kernel_platform`'овский
# `OutboxMessage` (ADR 0021) — так тесты (`Base.metadata.create_all`) и
# hand-written Alembic-ревизия видят все таблицы catalog-service вместе.


class ProductModel(Base):
    __tablename__ = "products"
    __table_args__ = (
        Index("ix_products_category", "category"),
        Index("ix_products_price", "price"),
        Index("ix_products_user_id", "user_id"),
        Index("ix_products_is_active_created_at_id", "is_active", "created_at", "id"),
    )

    id: Mapped[int] = mapped_column(BigInteger, Identity(), primary_key=True)
    name: Mapped[str] = mapped_column(String(100))
    category: Mapped[str] = mapped_column(String(100))
    price: Mapped[float]
    description: Mapped[str] = mapped_column(Text, default="", server_default="")
    user_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True))
    is_active: Mapped[bool] = mapped_column(default=True, server_default="true")
    created_at: Mapped[datetime] = mapped_column(server_default=func.now())
