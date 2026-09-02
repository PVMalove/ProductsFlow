"""Transport-neutral image DTOs for image command and query handlers."""

from dataclasses import dataclass
from datetime import datetime


@dataclass(frozen=True)
class ProductImageView:
    image_url: str
    updated_at: datetime


@dataclass(frozen=True)
class ProductImageMutation:
    replaced: bool
