import uuid

from fastapi import Query, UploadFile
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
    DeleteProductImageCommand,
    UpdateProductCommand,
    UpsertProductImageCommand,
)
from application.errors import (
    ProductImageTooLargeError,
    ProductImageUnsupportedMediaTypeError,
    ProductListCursorConflictError,
    ProductListInvalidCursorError,
)
from application.ports import Actor
from application.queries import (
    GetProductAuditQuery,
    GetProductImageQuery,
    GetProductQuery,
    ListProductsQuery,
)

_ALLOWED_IMAGE_CONTENT_TYPES = frozenset({"image/jpeg", "image/png", "image/webp"})
_MAX_IMAGE_SIZE = 5 * 1024 * 1024


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


class ProductImageGetRequest(BaseModel):
    """Path-bound — без JSON body, `product_id` приходит из URL."""

    product_id: uuid.UUID

    def to_query(self, *, actor: Actor | None) -> GetProductImageQuery:
        return GetProductImageQuery(product_id=self.product_id, actor=actor)


class ProductImageDeleteRequest(BaseModel):
    """Path-bound — без JSON body, `product_id` приходит из URL."""

    product_id: uuid.UUID

    def to_command(self, *, actor: Actor) -> DeleteProductImageCommand:
        return DeleteProductImageCommand(product_id=self.product_id, actor=actor)


class ProductImageUploadRequest(BaseModel):
    """Path-bound — `product_id` приходит из URL; сам multipart-файл не
    Pydantic-поле (FastAPI требует `UploadFile` отдельным параметром роута),
    но вся его транспортная валидация (тип, размер) всё равно инкапсулирована
    здесь, а не в роутере."""

    product_id: uuid.UUID

    async def to_command(
        self, *, file: UploadFile, actor: Actor
    ) -> UpsertProductImageCommand:
        if file.content_type not in _ALLOWED_IMAGE_CONTENT_TYPES:
            raise ProductImageUnsupportedMediaTypeError
        body = await file.read(_MAX_IMAGE_SIZE + 1)
        if len(body) > _MAX_IMAGE_SIZE:
            raise ProductImageTooLargeError
        return UpsertProductImageCommand(
            product_id=self.product_id,
            actor=actor,
            body=body,
            content_type=file.content_type,
        )

    def to_query(self, *, actor: Actor) -> GetProductImageQuery:
        """Строит последующий read-side query для того же `product_id` —
        роутер перечитывает View через `GetProductImageQueryHandler` после
        коммита upsert'а (разделение command/query, см. `product_images.py`)."""
        return GetProductImageQuery(product_id=self.product_id, actor=actor)
