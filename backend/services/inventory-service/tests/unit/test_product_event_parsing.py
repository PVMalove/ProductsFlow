"""Чистая функция парсинга `product.created.v2` (issue #367), по образцу
catalog-worker's `_parse_user_event_snapshot` — толерантна к лишним полям
снапшота, нужен только `product_id`."""

import json
import uuid

import pytest

from api.worker import parse_product_created_snapshot


def test_parse_product_created_snapshot_extracts_product_id() -> None:
    product_id = uuid.uuid4()
    body = json.dumps(
        {
            "product_id": str(product_id),
            "user_id": str(uuid.uuid4()),
            "name": "Товар",
            "price": 10.0,
        }
    ).encode()

    parsed = parse_product_created_snapshot(body)

    assert parsed == product_id


def test_parse_product_created_snapshot_rejects_missing_product_id() -> None:
    with pytest.raises(ValueError):
        parse_product_created_snapshot(json.dumps({"name": "Товар"}).encode())


def test_parse_product_created_snapshot_rejects_invalid_product_id() -> None:
    with pytest.raises(ValueError):
        parse_product_created_snapshot(
            json.dumps({"product_id": "not-a-uuid"}).encode()
        )


def test_parse_product_created_snapshot_rejects_invalid_json() -> None:
    with pytest.raises(ValueError):
        parse_product_created_snapshot(b"not-json")


def test_parse_product_created_snapshot_rejects_non_object_payload() -> None:
    with pytest.raises(ValueError):
        parse_product_created_snapshot(json.dumps([1, 2, 3]).encode())
