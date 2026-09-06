import uuid
from datetime import UTC, datetime

import pytest

from api.schemas import ProductListRequest
from application.catalog_list_cursor import (
    CatalogListCursor,
    ProductListSortOption,
    encode_catalog_cursor,
)
from application.errors import (
    ProductListCursorConflictError,
    ProductListInvalidCursorError,
)
from application.queries import ListProductsQuery


def test_list_request_to_query_carries_limit_and_no_cursor() -> None:
    request = ProductListRequest(limit=10, after=None, before=None)

    query = request.to_query()

    assert query == ListProductsQuery(limit=10, after=None, before=None)


def test_list_request_to_query_decodes_after_cursor() -> None:
    cursor_created_at = datetime(2026, 1, 1, tzinfo=UTC)
    cursor_id = uuid.uuid4()
    cursor = CatalogListCursor(
        sort=ProductListSortOption.NEWEST,
        sort_value=cursor_created_at.isoformat(),
        product_id=cursor_id,
    )
    token = encode_catalog_cursor(cursor)
    request = ProductListRequest(limit=20, after=token, before=None)

    query = request.to_query()

    assert query.after is not None
    assert query.after.sort == ProductListSortOption.NEWEST
    assert query.after.sort_value == cursor_created_at.isoformat()
    assert query.after.product_id == cursor_id
    assert query.before is None


def test_list_request_to_query_rejects_conflicting_cursors() -> None:
    request = ProductListRequest(limit=20, after="a", before="b")

    with pytest.raises(ProductListCursorConflictError):
        request.to_query()


def test_list_request_to_query_rejects_an_invalid_cursor() -> None:
    request = ProductListRequest(limit=20, after="not-a-valid-cursor", before=None)

    with pytest.raises(ProductListInvalidCursorError):
        request.to_query()
