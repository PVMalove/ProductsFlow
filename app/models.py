import enum
from datetime import datetime

from sqlalchemy import ForeignKey, func
from sqlalchemy.orm import DeclarativeBase, Mapped, mapped_column, relationship


class Base(DeclarativeBase):
    pass


class UserRole(enum.StrEnum):
    ADMIN = "admin"
    USER = "user"


class User(Base):
    __tablename__ = "users"

    id: Mapped[int] = mapped_column(primary_key=True)
    username: Mapped[str] = mapped_column(unique=True)
    password_hash: Mapped[str]
    role: Mapped[UserRole] = mapped_column(default=UserRole.USER)
    is_active: Mapped[bool] = mapped_column(default=True)
    created_at: Mapped[datetime] = mapped_column(server_default=func.now())
    updated_at: Mapped[datetime] = mapped_column(
        server_default=func.now(), onupdate=func.now()
    )


class Product(Base):
    __tablename__ = "products"

    id: Mapped[int] = mapped_column(primary_key=True)
    name: Mapped[str]
    category: Mapped[str]
    price: Mapped[float]
    description: Mapped[str] = mapped_column(default="", server_default="")
    user_id: Mapped[int] = mapped_column(ForeignKey("users.id"))
    is_active: Mapped[bool] = mapped_column(default=True)
    created_at: Mapped[datetime] = mapped_column(server_default=func.now())

    image: Mapped["ProductImage | None"] = relationship(
        back_populates="product",
        uselist=False,
        cascade="all, delete-orphan",
    )


class ProductImage(Base):
    __tablename__ = "product_image"

    id: Mapped[int] = mapped_column(primary_key=True)
    product_id: Mapped[int] = mapped_column(
        ForeignKey("products.id", ondelete="CASCADE"),
        unique=True,
    )
    s3_key: Mapped[str]
    content_type: Mapped[str]
    size_bytes: Mapped[int]
    created_at: Mapped[datetime] = mapped_column(server_default=func.now())
    updated_at: Mapped[datetime] = mapped_column(
        server_default=func.now(),
        onupdate=func.now(),
    )

    product: Mapped["Product"] = relationship(back_populates="image")


class UserAuditAction(enum.StrEnum):
    REGISTERED = "registered"
    PASSWORD_CHANGED = "password_changed"
    ACTIVATED = "activated"
    DEACTIVATED = "deactivated"


class UserAuditLog(Base):
    __tablename__ = "user_audit_logs"
    id: Mapped[int] = mapped_column(primary_key=True)
    user_id: Mapped[int] = mapped_column(ForeignKey("users.id"))
    actor_user_id: Mapped[int] = mapped_column(ForeignKey("users.id"))
    action: Mapped[UserAuditAction]
    description: Mapped[str] = mapped_column(default="", server_default="")
    created_at: Mapped[datetime] = mapped_column(server_default=func.now())


class ProductAuditAction(enum.StrEnum):
    CREATED = "created"
    UPDATED = "updated"
    DELETED = "deleted"
    ACTIVATED = "activated"
    DEACTIVATED = "deactivated"


class ProductAuditLog(Base):
    __tablename__ = "product_audit_log"
    id: Mapped[int] = mapped_column(primary_key=True)
    # Без ForeignKey: после DELETED продукта строка в products уже отсутствует,
    # и с PRAGMA foreign_keys=ON вставка в этот момент нарушила бы ограничение.
    product_id: Mapped[int]
    actor_user_id: Mapped[int] = mapped_column(ForeignKey("users.id"))
    action: Mapped[ProductAuditAction]
    description: Mapped[str] = mapped_column(default="", server_default="")
    created_at: Mapped[datetime] = mapped_column(server_default=func.now())
