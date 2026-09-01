import uuid
from datetime import datetime

from pydantic import BaseModel

from application.image_dto import ProductImageView
from application.ports import ProductAuditAction, ProductAuditEntry
from domain.product import Product
from domain.repositories import PageInfo, ProductPage


class ProductCreateRequest(BaseModel):
    name: str
    description: str = ""
    price: float
    category: str


class ProductUpdateRequest(BaseModel):
    """Все поля опциональны — `PATCH` частичный, отсутствующее поле не
    трогается (`exclude_unset` на стороне роутера, CONTEXT.md «Обновление
    товара»)."""

    name: str | None = None
    description: str | None = None
    price: float | None = None
    category: str | None = None


class ProductResponse(BaseModel):
    id: uuid.UUID
    name: str
    description: str
    price: float
    category: str
    user_id: uuid.UUID
    is_active: bool

    @classmethod
    def from_domain(cls, product: Product) -> "ProductResponse":
        return cls(
            id=product.id.value,
            name=product.name,
            description=product.description,
            price=product.price,
            category=product.category,
            user_id=product.user_id,
            is_active=product.is_active,
        )


class PageInfoResponse(BaseModel):
    next_cursor: str | None
    prev_cursor: str | None
    has_more: bool
    has_prev: bool

    @classmethod
    def from_domain(cls, page_info: PageInfo) -> "PageInfoResponse":
        return cls(
            next_cursor=page_info.next_cursor,
            prev_cursor=page_info.prev_cursor,
            has_more=page_info.has_more,
            has_prev=page_info.has_prev,
        )


class ProductListResponse(BaseModel):
    items: list[ProductResponse]
    page_info: PageInfoResponse

    @classmethod
    def from_domain(cls, page: ProductPage) -> "ProductListResponse":
        return cls(
            items=[ProductResponse.from_domain(item) for item in page.items],
            page_info=PageInfoResponse.from_domain(page.page_info),
        )


class ProductAuditLogResponse(BaseModel):
    id: int
    product_id: uuid.UUID
    actor_user_id: uuid.UUID | None
    action: ProductAuditAction
    description: str
    created_at: datetime

    @classmethod
    def from_entry(cls, row: ProductAuditEntry) -> "ProductAuditLogResponse":
        return cls(
            id=row.id,
            product_id=row.product_id,
            actor_user_id=row.actor_user_id,
            action=row.action,
            description=row.description,
            created_at=row.created_at,
        )


class ProductImageResponse(BaseModel):
    image_url: str
    updated_at: datetime

    @classmethod
    def from_view(cls, view: ProductImageView) -> "ProductImageResponse":
        return cls(image_url=view.image_url, updated_at=view.updated_at)
