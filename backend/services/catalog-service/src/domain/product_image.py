from dataclasses import dataclass
from datetime import datetime

from domain.product_id import ProductId


@dataclass(frozen=True)
class ProductImage:
    """The single image record belonging to a Product aggregate."""

    product_id: ProductId
    s3_key: str
    content_type: str
    size_bytes: int
    created_at: datetime
    updated_at: datetime
