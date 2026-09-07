import base64
import binascii
import json
import math
import uuid
from datetime import datetime

from domain.repositories import CatalogListCursor, ProductListSortOption


class InvalidCatalogCursorError(ValueError):
    """Некорректный курсор витрины."""


def encode_catalog_cursor(cursor: CatalogListCursor) -> str:
    sort_value = (
        cursor.sort_value.isoformat()
        if isinstance(cursor.sort_value, datetime)
        else cursor.sort_value
    )
    raw = json.dumps([cursor.sort.value, sort_value, str(cursor.product_id)])
    return base64.urlsafe_b64encode(raw.encode("utf-8")).decode("ascii")


def _decode_sort_value(sort: ProductListSortOption, value: object) -> datetime | float:
    if sort is ProductListSortOption.NEWEST:
        if not isinstance(value, str):
            raise TypeError("Курсор newest должен содержать дату")
        return datetime.fromisoformat(value)

    if isinstance(value, bool) or not isinstance(value, (int, float)):
        raise TypeError("Цена курсора должна быть числом")
    parsed_price = float(value)
    if not math.isfinite(parsed_price):
        raise ValueError("Цена курсора должна быть конечным числом")
    return parsed_price


def decode_catalog_cursor(
    token: str, *, expected_sort: ProductListSortOption
) -> CatalogListCursor:
    try:
        raw = base64.b64decode(
            token.encode("ascii"), altchars=b"-_", validate=True
        ).decode("utf-8")
        sort_raw, value_raw, id_raw = json.loads(raw)
        sort = ProductListSortOption(sort_raw)
        if sort is not expected_sort:
            raise ValueError("Курсор закодирован под другую сортировку")
        if not isinstance(id_raw, str):
            raise TypeError("ID товара в курсоре должен быть строкой")
        return CatalogListCursor(
            sort=sort,
            sort_value=_decode_sort_value(sort, value_raw),
            product_id=uuid.UUID(id_raw),
        )
    except (
        ValueError,
        TypeError,
        binascii.Error,
        UnicodeError,
        json.JSONDecodeError,
    ) as exc:
        raise InvalidCatalogCursorError("Некорректный курсор пагинации") from exc
