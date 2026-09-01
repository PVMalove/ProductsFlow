"""Compatibility exports for the cursor contract.

Cursor serialization is an application/API concern; this module remains as a
stable import path for existing infrastructure tests and callers.
"""

from application.pagination import (
    DEFAULT_PAGE_LIMIT,
    MAX_PAGE_LIMIT,
    Cursor,
    InvalidCursorError,
    decode_cursor,
    encode_cursor,
)
from domain.repositories import PageInfo, ProductPage


__all__ = [
    "DEFAULT_PAGE_LIMIT",
    "MAX_PAGE_LIMIT",
    "Cursor",
    "InvalidCursorError",
    "PageInfo",
    "ProductPage",
    "decode_cursor",
    "encode_cursor",
]
