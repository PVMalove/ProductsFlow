import uuid
from dataclasses import dataclass


@dataclass(frozen=True)
class ProductSearchSnapshot:
    """The self-contained state of a Product projected into public search."""

    product_id: uuid.UUID
    user_id: uuid.UUID
    name: str
    description: str
    category: str
    price: float
    is_active: bool
    search_revision: int
