import uuid
from dataclasses import dataclass
from datetime import datetime
from typing import Any

from kernel_domain.domain_event import DomainEvent

from domain.value_objects.product_id import ProductId


@dataclass(frozen=True, kw_only=True)
class ProductEvent(DomainEvent):
    """Общий предок Product-событий — все они несут `product_id`; выделено,
    чтобы код, читающий события единообразно (например, generic drain в
    Outbox, ADR 0006/0011), мог опираться на поле `product_id`, не различая
    конкретный подкласс через `isinstance`. Реализует часть общего
    контракта `DomainEvent`, общую для всех Product-событий: `aggregate_type`
    и маппинг `product_id` в `aggregate_id()`/базовый `to_payload()`."""

    aggregate_type: str = "Product"

    product_id: ProductId

    def aggregate_id(self) -> uuid.UUID:
        return self.product_id.value

    def to_payload(self) -> dict[str, Any]:
        return {"product_id": str(self.product_id.value)}


@dataclass(frozen=True, kw_only=True)
class ProductSnapshotEvent(ProductEvent):
    """Self-contained search snapshot emitted with each indexable mutation."""

    user_id: uuid.UUID
    name: str
    description: str
    category: str
    price: float
    is_active: bool
    search_revision: int
    created_at: datetime

    def to_payload(self) -> dict[str, Any]:
        return {
            **super().to_payload(),
            "user_id": str(self.user_id),
            "name": self.name,
            "description": self.description,
            "category": self.category,
            "price": self.price,
            "is_active": self.is_active,
            "search_revision": self.search_revision,
            "created_at": self.created_at.isoformat(),
        }


@dataclass(frozen=True, kw_only=True)
class ProductCreated(ProductSnapshotEvent):
    event_type: str = "product.created.v2"


@dataclass(frozen=True, kw_only=True)
class ProductUpdated(ProductSnapshotEvent):
    event_type: str = "product.updated.v2"


@dataclass(frozen=True, kw_only=True)
class ProductActivated(ProductSnapshotEvent):
    event_type: str = "product.activated.v2"


@dataclass(frozen=True, kw_only=True)
class ProductDeactivated(ProductSnapshotEvent):
    event_type: str = "product.deactivated.v2"


@dataclass(frozen=True, kw_only=True)
class ProductDeleted(ProductEvent):
    event_type: str = "product.deleted.v1"
