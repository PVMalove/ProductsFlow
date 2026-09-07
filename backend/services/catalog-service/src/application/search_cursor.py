# ruff: noqa: E501
"""Непрозрачный `search_after`-курсор публичного поиска (issue #291).

В отличие от общего keyset-курсора `kernel_platform.pagination` (всегда
`(created_at, id)`), позиция в поиске зависит от текущей сортировки —
релевантность, цена или новизна каждая используют своё поле. Курсор несёт
и режим сортировки, и её значение на границе страницы, и Product ID как
обязательный тай-брейкер (ADR-декларация epic #283)."""

import base64
import binascii
import enum
import json
import uuid
from dataclasses import dataclass


class ProductSortOption(enum.StrEnum):
    RELEVANCE = "relevance"
    PRICE_ASC = "price_asc"
    PRICE_DESC = "price_desc"
    NEWEST = "newest"


def resolve_search_sort(
    query: str | None, sort: ProductSortOption | None
) -> ProductSortOption:
    """Selects the public search default without overriding an explicit sort."""
    if sort is not None:
        return sort
    return (
        ProductSortOption.RELEVANCE
        if query and query.strip()
        else ProductSortOption.NEWEST
    )


@dataclass(frozen=True)
class SearchCursor:
    """Keyset-позиция публичного поиска — граница текущей сортировки плюс
    Product ID, тай-брейкер, завершающий OpenSearch `search_after` (issue #291)."""

    sort: ProductSortOption
    sort_value: float
    product_id: uuid.UUID


class InvalidSearchCursorError(ValueError):
    """Курсор поиска повреждён или закодирован под другую сортировку."""


def encode_search_cursor(cursor: SearchCursor) -> str:
    """Кодирует позицию поиска в непрозрачный курсор (см. `decode_search_cursor`)."""
    raw = json.dumps([cursor.sort.value, cursor.sort_value, str(cursor.product_id)])
    return base64.urlsafe_b64encode(raw.encode("utf-8")).decode("ascii")


def decode_search_cursor(
    token: str, *, expected_sort: ProductSortOption
) -> SearchCursor:
    """Декодирует курсор, выданный `encode_search_cursor`.

    Raises:
        InvalidSearchCursorError: курсор повреждён, либо закодирован под
            сортировку, отличную от `expected_sort` (issue #291 acceptance
            criterion — смешанные cursor-параметры отклоняются)."""
    try:
        raw = base64.urlsafe_b64decode(token.encode("ascii")).decode("utf-8")
        sort_raw, value_raw, id_raw = json.loads(raw)
        sort = ProductSortOption(sort_raw)
        if sort is not expected_sort:
            raise ValueError("Курсор закодирован под другую сортировку")
        return SearchCursor(
            sort=sort,
            sort_value=float(value_raw),
            product_id=uuid.UUID(id_raw),
        )
    except (
        ValueError,
        TypeError,
        binascii.Error,
        UnicodeDecodeError,
        json.JSONDecodeError,
    ) as exc:
        raise InvalidSearchCursorError("Некорректный курсор поиска") from exc
