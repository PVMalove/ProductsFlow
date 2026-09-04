# ruff: noqa: E501
"""Transport-neutral DTO картинки для command и query handler'ов картинки."""

from dataclasses import dataclass
from datetime import datetime


@dataclass(frozen=True)
class ProductImageView:
    image_url: str
    updated_at: datetime


@dataclass(frozen=True)
class ProductImageMutation:
    replaced: bool
