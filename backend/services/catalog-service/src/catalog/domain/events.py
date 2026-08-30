import uuid
from dataclasses import dataclass

from kernel_domain.domain_event import DomainEvent

from catalog.domain.product_id import ProductId


@dataclass(frozen=True, kw_only=True)
class ProductCreated(DomainEvent):
    product_id: ProductId
    user_id: uuid.UUID
    name: str
    category: str
    price: float


@dataclass(frozen=True, kw_only=True)
class ProductUpdated(DomainEvent):
    product_id: ProductId


@dataclass(frozen=True, kw_only=True)
class ProductActivated(DomainEvent):
    product_id: ProductId


@dataclass(frozen=True, kw_only=True)
class ProductDeactivated(DomainEvent):
    product_id: ProductId


@dataclass(frozen=True, kw_only=True)
class ProductDeleted(DomainEvent):
    product_id: ProductId
