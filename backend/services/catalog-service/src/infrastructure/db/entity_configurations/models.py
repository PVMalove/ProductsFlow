import uuid
from datetime import datetime

from kernel_platform.outbox.models import Base
from sqlalchemy import (
    BigInteger,
    ForeignKey,
    Identity,
    Index,
    Integer,
    String,
    Text,
    func,
)
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.orm import Mapped, mapped_column

# Тот же `Base` (и, значит, `Base.metadata`), что и `kernel_platform`'овский
# `OutboxMessage` (ADR 0010) — так тесты (`Base.metadata.create_all`) и
# написанная вручную Alembic-ревизия видят все таблицы catalog-service вместе.


class ProductModel(Base):
    __tablename__ = "products"
    __table_args__ = (
        Index("ix_products_category", "category"),
        Index("ix_products_price", "price"),
        Index("ix_products_user_id", "user_id"),
        Index("ix_products_is_active_created_at_id", "is_active", "created_at", "id"),
    )

    id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), primary_key=True, default=uuid.uuid4
    )
    name: Mapped[str] = mapped_column(String(100))
    category: Mapped[str] = mapped_column(String(100))
    price: Mapped[float]
    description: Mapped[str] = mapped_column(Text, default="", server_default="")
    user_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True))
    is_active: Mapped[bool] = mapped_column(default=True, server_default="true")
    created_at: Mapped[datetime] = mapped_column(server_default=func.now())


class ProductImageModel(Base):
    __tablename__ = "product_images"

    id: Mapped[int] = mapped_column(BigInteger, Identity(), primary_key=True)
    product_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("products.id", ondelete="CASCADE"), unique=True
    )
    s3_key: Mapped[str] = mapped_column(String(512))
    content_type: Mapped[str] = mapped_column(String(100))
    size_bytes: Mapped[int] = mapped_column(Integer)
    created_at: Mapped[datetime] = mapped_column(server_default=func.now())
    updated_at: Mapped[datetime] = mapped_column(
        server_default=func.now(), onupdate=func.now()
    )
