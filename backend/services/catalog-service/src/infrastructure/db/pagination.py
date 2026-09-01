"""Compatibility exports for the application-owned pagination DTOs."""

from application.pagination import (
    DEFAULT_PAGE_LIMIT,
    MAX_PAGE_LIMIT,
    Cursor,
    InvalidCursorError,
    PageInfo,
    ProductPage,
    decode_cursor,
    encode_cursor,
)

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
