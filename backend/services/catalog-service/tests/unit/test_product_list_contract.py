import base64
import json
import uuid
from datetime import UTC, datetime

import pytest

from api.schemas import ProductListRequest
from application.catalog_list_cursor import encode_catalog_cursor
from application.errors import (
    ProductListCursorConflictError,
    ProductListInvalidCursorError,
)
from application.queries import ListProductsQuery
from domain.repositories import CatalogListCursor, ProductListSortOption


def test_list_request_to_query_carries_limit_and_no_cursor() -> None:
    request = ProductListRequest(limit=10, after=None, before=None)

    query = request.to_query()

    assert query == ListProductsQuery(limit=10, after=None, before=None)


def test_list_request_to_query_decodes_after_cursor() -> None:
    cursor_created_at = datetime(2026, 1, 1, tzinfo=UTC)
    cursor_id = uuid.uuid4()
    cursor = CatalogListCursor(
        sort=ProductListSortOption.NEWEST,
        sort_value=cursor_created_at,
        product_id=cursor_id,
    )
    token = encode_catalog_cursor(cursor)
    request = ProductListRequest(limit=20, after=token, before=None)

    query = request.to_query()

    assert query.after is not None
    assert query.after.sort == ProductListSortOption.NEWEST
    assert query.after.sort_value == cursor_created_at
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


@pytest.mark.parametrize(
    "payload",
    [
        [ProductListSortOption.NEWEST.value, "2026-01-01T00:00:00", None],
        [ProductListSortOption.NEWEST.value, "2026-01-01T00:00:00", 123],
    ],
)
def test_list_request_rejects_a_non_string_product_id(payload: list[object]) -> None:
    raw = json.dumps(payload)
    token = base64.urlsafe_b64encode(raw.encode()).decode()

    with pytest.raises(ProductListInvalidCursorError):
        ProductListRequest(after=token).to_query()


def test_list_request_rejects_a_non_ascii_cursor() -> None:
    with pytest.raises(ProductListInvalidCursorError):
        ProductListRequest(after="курсор").to_query()


@pytest.mark.parametrize(
    ("sort", "sort_value"),
    [
        (ProductListSortOption.NEWEST, "invalid"),
        (ProductListSortOption.NEWEST, None),
        (ProductListSortOption.PRICE_ASC, "invalid"),
        (ProductListSortOption.PRICE_DESC, None),
        (ProductListSortOption.PRICE_ASC, float("nan")),
    ],
)
def test_list_request_rejects_an_invalid_sort_value(
    sort: ProductListSortOption, sort_value: object
) -> None:
    raw = json.dumps([sort.value, sort_value, str(uuid.uuid4())])
    token = base64.urlsafe_b64encode(raw.encode()).decode()
    request = ProductListRequest(sort=sort, after=token)

    with pytest.raises(ProductListInvalidCursorError):
        request.to_query()


@pytest.mark.parametrize(
    "sort", [ProductListSortOption.PRICE_ASC, ProductListSortOption.PRICE_DESC]
)
def test_list_request_decodes_price_sort_value_as_float(
    sort: ProductListSortOption,
) -> None:
    cursor = CatalogListCursor(sort=sort, sort_value=42.5, product_id=uuid.uuid4())

    query = ProductListRequest(
        sort=sort, after=encode_catalog_cursor(cursor)
    ).to_query()

    assert query.after is not None
    assert query.after.sort_value == 42.5
