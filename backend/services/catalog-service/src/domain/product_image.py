from dataclasses import dataclass
from datetime import datetime

from domain.value_objects.product_id import ProductId


@dataclass(frozen=True)
class ProductImage:
    """Единственная запись картинки, принадлежащая агрегату Product."""

    product_id: ProductId
    s3_key: str
    content_type: str
    size_bytes: int
    created_at: datetime
    updated_at: datetime
