# ruff: noqa: E501
import base64
import binascii
import uuid
from datetime import datetime

from domain.repositories import Cursor

DEFAULT_PAGE_LIMIT = 20
MAX_PAGE_LIMIT = 100


class InvalidCursorError(ValueError):
    """The pagination cursor could not be decoded."""


def encode_cursor(created_at: datetime, product_id: uuid.UUID) -> str:
    raw = f"{created_at.isoformat()}|{product_id}"
    return base64.urlsafe_b64encode(raw.encode("utf-8")).decode("ascii")


def decode_cursor(token: str) -> Cursor:
    try:
        raw = base64.urlsafe_b64decode(token.encode("ascii")).decode("utf-8")
        created_at_raw, id_raw = raw.split("|")
        return Cursor(
            created_at=datetime.fromisoformat(created_at_raw), id=uuid.UUID(id_raw)
        )
    except (ValueError, binascii.Error, UnicodeDecodeError) as exc:
        raise InvalidCursorError("Некорректный курсор пагинации") from exc


__all__ = [
    "DEFAULT_PAGE_LIMIT",
    "MAX_PAGE_LIMIT",
    "Cursor",
    "InvalidCursorError",
    "decode_cursor",
    "encode_cursor",
]
