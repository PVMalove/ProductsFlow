import uuid

from fastapi import Query
from kernel_platform.pagination import (
    DEFAULT_PAGE_LIMIT,
    MAX_PAGE_LIMIT,
    InvalidCursorError,
    decode_cursor,
)
from pydantic import BaseModel

from application.commands import (
    ActivateProductCommand,
    CreateProductCommand,
    DeactivateProductCommand,
    DeleteProductCommand,
    UpdateProductCommand,
)
from application.errors import (
    ProductListCursorConflictError,
    ProductListInvalidCursorError,
)
from application.ports import Actor
from application.queries import GetProductAuditQuery, GetProductQuery, ListProductsQuery


class ProductCreateRequest(BaseModel):
    name: str
    description: str = ""
    price: float
    category: str

    def to_command(self, *, actor: Actor) -> CreateProductCommand:
        return CreateProductCommand(
            actor=actor,
            name=self.name,
            description=self.description,
            price=self.price,
            category=self.category,
        )


class ProductUpdateRequest(BaseModel):
    """Все поля опциональны — `PATCH` частичный, отсутствующее поле не
    трогается (`exclude_unset` внутри `to_command`, CONTEXT.md «Обновление
    товара»)."""

    name: str | None = None
    description: str | None = None
    price: float | None = None
    category: str | None = None

    def to_command(
        self, *, product_id: uuid.UUID, actor: Actor
    ) -> UpdateProductCommand:
        return UpdateProductCommand(
            product_id=product_id,
            actor=actor,
            **self.model_dump(exclude_unset=True),
        )


class ProductActivateRequest(BaseModel):
    """Path-bound — без JSON body, `product_id` приходит из URL."""

    product_id: uuid.UUID

    def to_command(self, *, actor: Actor) -> ActivateProductCommand:
        return ActivateProductCommand(product_id=self.product_id, actor=actor)


class ProductDeactivateRequest(BaseModel):
    product_id: uuid.UUID

    def to_command(self, *, actor: Actor) -> DeactivateProductCommand:
        return DeactivateProductCommand(product_id=self.product_id, actor=actor)


class ProductDeleteRequest(BaseModel):
    product_id: uuid.UUID

    def to_command(self, *, actor: Actor) -> DeleteProductCommand:
        return DeleteProductCommand(product_id=self.product_id, actor=actor)


class ProductGetRequest(BaseModel):
    """Path-bound — без JSON body, `product_id` приходит из URL."""

    product_id: uuid.UUID

    def to_query(self, *, actor: Actor | None) -> GetProductQuery:
        return GetProductQuery(product_id=self.product_id, actor=actor)


class ProductListRequest(BaseModel):
    """Query-bound — без path/body, `limit`/`after`/`before` приходят из
    query-строки (issue #221)."""

    limit: int = Query(default=DEFAULT_PAGE_LIMIT, ge=1, le=MAX_PAGE_LIMIT)
    after: str | None = Query(default=None)
    before: str | None = Query(default=None)

    def to_query(self) -> ListProductsQuery:
        if self.after is not None and self.before is not None:
            raise ProductListCursorConflictError
        try:
            after_cursor = decode_cursor(self.after) if self.after is not None else None
            before_cursor = (
                decode_cursor(self.before) if self.before is not None else None
            )
        except InvalidCursorError as exc:
            raise ProductListInvalidCursorError from exc
        return ListProductsQuery(
            limit=self.limit, after=after_cursor, before=before_cursor
        )


class ProductAuditRequest(BaseModel):
    """Path-bound — без JSON body, `product_id` приходит из URL."""

    product_id: uuid.UUID

    def to_query(self, *, actor: Actor) -> GetProductAuditQuery:
        return GetProductAuditQuery(product_id=self.product_id, actor=actor)
