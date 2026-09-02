import uuid
from dataclasses import dataclass
from typing import Any

from kernel_domain.domain_event import DomainEvent

from domain.product_id import ProductId


@dataclass(frozen=True, kw_only=True)
class ProductEvent(DomainEvent):
    """Общий предок Product-событий — все они несут `product_id`; выделено,
    чтобы код, читающий события единообразно (например, generic drain в
    Outbox, ADR 0029), мог опираться на поле `product_id`, не различая
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
class ProductCreated(ProductEvent):
    event_type: str = "product.created.v1"

    user_id: uuid.UUID
    name: str
    category: str
    price: float

    def to_payload(self) -> dict[str, Any]:
        return {
            **super().to_payload(),
            "user_id": str(self.user_id),
            "name": self.name,
            "category": self.category,
            "price": self.price,
        }


@dataclass(frozen=True, kw_only=True)
class ProductUpdated(ProductEvent):
    event_type: str = "product.updated.v1"


@dataclass(frozen=True, kw_only=True)
class ProductActivated(ProductEvent):
    event_type: str = "product.activated.v1"


@dataclass(frozen=True, kw_only=True)
class ProductDeactivated(ProductEvent):
    event_type: str = "product.deactivated.v1"


@dataclass(frozen=True, kw_only=True)
class ProductDeleted(ProductEvent):
    event_type: str = "product.deleted.v1"
