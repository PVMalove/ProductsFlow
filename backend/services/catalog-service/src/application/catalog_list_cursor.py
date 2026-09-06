import base64
import json
import uuid

from domain.repositories import CatalogListCursor, ProductListSortOption


class InvalidCatalogCursorError(ValueError):
    """Некорректный курсор витрины."""


def encode_catalog_cursor(cursor: CatalogListCursor) -> str:
    raw = json.dumps([cursor.sort.value, cursor.sort_value, str(cursor.product_id)])
    return base64.urlsafe_b64encode(raw.encode("utf-8")).decode("ascii")


def decode_catalog_cursor(
    token: str, *, expected_sort: ProductListSortOption
) -> CatalogListCursor:
    try:
        raw = base64.urlsafe_b64decode(token.encode("ascii")).decode("utf-8")
        sort_raw, value_raw, id_raw = json.loads(raw)
        sort = ProductListSortOption(sort_raw)
        if sort is not expected_sort:
            raise ValueError("Курсор закодирован под другую сортировку")
        return CatalogListCursor(
            sort=sort,
            sort_value=value_raw,
            product_id=uuid.UUID(id_raw),
        )
    except Exception as exc:
        raise InvalidCatalogCursorError("Некорректный курсор пагинации") from exc
