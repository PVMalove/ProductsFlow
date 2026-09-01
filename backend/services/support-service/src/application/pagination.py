import base64
import binascii
import uuid
from datetime import datetime

from domain.repositories import Cursor

DEFAULT_PAGE_LIMIT = 20
MAX_PAGE_LIMIT = 100


class InvalidCursorError(ValueError):
    """The pagination cursor is malformed."""


def encode_cursor(created_at: datetime, item_id: uuid.UUID) -> str:
    raw = f"{created_at.isoformat()}|{item_id}"
    return base64.urlsafe_b64encode(raw.encode("utf-8")).decode("ascii")


def decode_cursor(token: str) -> Cursor:
    try:
        raw = base64.urlsafe_b64decode(token.encode("ascii")).decode("utf-8")
        created_at, item_id = raw.split("|")
        return Cursor(datetime.fromisoformat(created_at), uuid.UUID(item_id))
    except (ValueError, binascii.Error, UnicodeDecodeError) as exc:
        raise InvalidCursorError("Некорректный курсор пагинации") from exc
