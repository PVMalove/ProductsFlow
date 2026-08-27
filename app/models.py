import enum
from datetime import datetime
from typing import TYPE_CHECKING

from sqlalchemy import DateTime, ForeignKey, String, func
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.database import Base

if TYPE_CHECKING:
    from app.support.models import Conversation, ConversationMessage


class UserRole(enum.StrEnum):
    ADMIN = "admin"
    USER = "user"


class User(Base):
    __tablename__ = "users"

    id: Mapped[int] = mapped_column(primary_key=True)
    username: Mapped[str] = mapped_column(String(50), unique=True)
    password_hash: Mapped[str] = mapped_column(String(255))
    role: Mapped[UserRole] = mapped_column(default=UserRole.USER)
    is_active: Mapped[bool] = mapped_column(default=True)

    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now()
    )

    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), onupdate=func.now()
    )

    created_conversations: Mapped[list["Conversation"]] = relationship(
        foreign_keys="[Conversation.created_by_user_id]",
        back_populates="creator",
    )

    assigned_conversations: Mapped[list["Conversation"]] = relationship(
        foreign_keys="[Conversation.assigned_admin_id]",
        back_populates="assignee",
    )

    messages: Mapped[list["ConversationMessage"]] = relationship(
        back_populates="sender",
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
    is_featured: Mapped[bool] = mapped_column(default=False, server_default="false")

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
    IMAGE_UPDATED = "image_updated"
    IMAGE_DELETED = "image_deleted"


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
