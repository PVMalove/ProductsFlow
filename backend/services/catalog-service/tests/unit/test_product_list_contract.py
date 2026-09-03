import uuid
from datetime import UTC, datetime

import pytest
from kernel_platform.pagination import encode_cursor

from api.schemas import ProductListRequest
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
    token = encode_cursor(cursor_created_at, cursor_id)
    request = ProductListRequest(limit=20, after=token, before=None)

    query = request.to_query()

    assert query.after is not None
    assert query.after.created_at == cursor_created_at
    assert query.after.id == cursor_id
    assert query.before is None


def test_list_request_to_query_rejects_conflicting_cursors() -> None:
    request = ProductListRequest(limit=20, after="a", before="b")

    with pytest.raises(ProductListCursorConflictError):
        request.to_query()


def test_list_request_to_query_rejects_an_invalid_cursor() -> None:
    request = ProductListRequest(limit=20, after="not-a-valid-cursor", before=None)

    with pytest.raises(ProductListInvalidCursorError):
        request.to_query()
