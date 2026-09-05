import json
import uuid
from typing import cast

import pytest
from aio_pika.abc import AbstractIncomingMessage

from api.search_worker import handle_product_event
from application.search_snapshot import ProductSearchSnapshot


class FakeMessage:
    def __init__(self, *, event_type: str, payload: dict[str, object]) -> None:
        self.type = event_type
        self.routing_key = event_type
        self.body = json.dumps(payload).encode()


class RecordingIndexer:
    def __init__(self) -> None:
        self.snapshots: list[ProductSearchSnapshot] = []

    async def index(self, snapshot: ProductSearchSnapshot) -> None:
        self.snapshots.append(snapshot)


@pytest.mark.asyncio
async def test_worker_indexes_a_complete_v2_product_snapshot() -> None:
    product_id = uuid.uuid4()
    owner_id = uuid.uuid4()
    indexer = RecordingIndexer()

    await handle_product_event(
        cast(
            AbstractIncomingMessage,
            FakeMessage(
                event_type="product.deactivated.v2",
                payload={
                    "product_id": str(product_id),
                    "user_id": str(owner_id),
                    "name": "Cordless drill",
                    "description": "18V brushless drill",
                    "category": "Tools",
                    "price": 99.0,
                    "is_active": False,
                    "search_revision": 4,
                },
            ),
        ),
        indexer,
    )

    assert indexer.snapshots == [
        ProductSearchSnapshot(
            product_id=product_id,
            user_id=owner_id,
            name="Cordless drill",
            description="18V brushless drill",
            category="Tools",
            price=99.0,
            is_active=False,
            search_revision=4,
        )
    ]
