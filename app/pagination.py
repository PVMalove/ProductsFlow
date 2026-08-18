import base64
import binascii
from dataclasses import dataclass
from datetime import datetime

# Общие для всех product-list-эндпоинтов дефолты (см. docs/adr/0001).
DEFAULT_PAGE_LIMIT = 20
MAX_PAGE_LIMIT = 100


class InvalidCursorError(ValueError):
    """Курсор пагинации не удалось декодировать — клиенту нужно вернуть 400."""


@dataclass(frozen=True)
class Cursor:
    """Непрозрачная keyset-позиция в списке продуктов: (created_at, id)."""

    created_at: datetime
    id: int


def encode_cursor(created_at: datetime, product_id: int) -> str:
    raw = f"{created_at.isoformat()}|{product_id}"
    return base64.urlsafe_b64encode(raw.encode("utf-8")).decode("ascii")


def decode_cursor(token: str) -> Cursor:
    try:
        raw = base64.urlsafe_b64decode(token.encode("ascii")).decode("utf-8")
        created_at_raw, id_raw = raw.split("|")
        return Cursor(created_at=datetime.fromisoformat(created_at_raw), id=int(id_raw))
    except (ValueError, binascii.Error, UnicodeDecodeError) as exc:
        raise InvalidCursorError("Некорректный курсор пагинации") from exc
