"""Transport-neutral image DTOs shared by image command and query handlers."""

from dataclasses import dataclass
from datetime import datetime


@dataclass(frozen=True)
class ProductImageView:
    image_url: str
    updated_at: datetime


@dataclass(frozen=True)
class ProductImageMutation:
    view: ProductImageView
    replaced: bool
