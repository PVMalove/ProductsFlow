import uuid
from dataclasses import dataclass

from kernel_domain.domain_event import DomainEvent

from catalog.domain.product_id import ProductId


@dataclass(frozen=True, kw_only=True)
class ProductEvent(DomainEvent):
    """Общий предок Product-событий — все они несут `product_id`; выделено,
    чтобы код, читающий события единообразно (например, маппинг в Outbox,
    ADR 0021), мог опираться на поле `product_id`, не различая конкретный
    подкласс через `isinstance`."""

    product_id: ProductId


@dataclass(frozen=True, kw_only=True)
class ProductCreated(ProductEvent):
    user_id: uuid.UUID
    name: str
    category: str
    price: float


@dataclass(frozen=True, kw_only=True)
class ProductUpdated(ProductEvent):
    pass


@dataclass(frozen=True, kw_only=True)
class ProductActivated(ProductEvent):
    pass


@dataclass(frozen=True, kw_only=True)
class ProductDeactivated(ProductEvent):
    pass


@dataclass(frozen=True, kw_only=True)
class ProductDeleted(ProductEvent):
    pass
