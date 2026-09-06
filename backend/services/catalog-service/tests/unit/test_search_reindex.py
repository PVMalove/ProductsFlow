import uuid
from collections.abc import AsyncIterator
from datetime import datetime

import pytest

from application.ports import SearchSnapshotWithOwner
from application.search_reindex import ReindexPolicy, SearchReindexJob
from application.search_snapshot import ProductSearchSnapshot


class SnapshotSource:
    def __init__(self, item: SearchSnapshotWithOwner) -> None:
        self.item = item
        self.calls = 0

    async def stream_batches(
        self, *, batch_size: int
    ) -> AsyncIterator[list[SearchSnapshotWithOwner]]:
        self.calls += 1
        yield [self.item]

    async def get(self, product_id: uuid.UUID) -> SearchSnapshotWithOwner | None:
        return self.item if self.item.snapshot.product_id == product_id else None


class RecordingReindexer:
    def __init__(self) -> None:
        self.calls: list[str] = []

    async def begin_reindex(self) -> None:
        self.calls.append("begin")

    async def index_rebuild(
        self, snapshot: ProductSearchSnapshot, *, owner_is_active: bool
    ) -> None:
        self.calls.append(f"rebuild:{snapshot.search_revision}:{owner_is_active}")

    async def complete_reindex(self) -> None:
        self.calls.append("complete")

    async def index(
        self, snapshot: ProductSearchSnapshot, *, owner_is_active: bool
    ) -> None:
        self.calls.append(f"live:{snapshot.search_revision}:{owner_is_active}")

    async def delete(self, _tombstone: object) -> None:
        raise AssertionError("not used")

    async def set_owner_active(self, _user_id: uuid.UUID, *, is_active: bool) -> None:
        raise AssertionError("not used")


@pytest.mark.asyncio
async def test_rebuild_reconciles_twice_before_an_atomic_alias_switch() -> None:
    item = SearchSnapshotWithOwner(
        snapshot=ProductSearchSnapshot(
            product_id=uuid.uuid4(),
            user_id=uuid.uuid4(),
            name="Drill",
            description="",
            category="Tools",
            price=10.0,
            is_active=True,
            search_revision=7,
            created_at=datetime(2026, 1, 1),
        ),
        owner_is_active=True,
    )
    source = SnapshotSource(item)
    indexer = RecordingReindexer()
    job = SearchReindexJob(
        source, indexer, policy=ReindexPolicy(batch_size=10, throttle_seconds=0)
    )

    await job.rebuild()

    assert indexer.calls == ["begin", "rebuild:7:True", "rebuild:7:True", "complete"]
    assert source.calls == 2


@pytest.mark.asyncio
async def test_nightly_reconciliation_repairs_active_alias_without_switching() -> None:
    item = SearchSnapshotWithOwner(
        snapshot=ProductSearchSnapshot(
            product_id=uuid.uuid4(),
            user_id=uuid.uuid4(),
            name="Drill",
            description="",
            category="Tools",
            price=10.0,
            is_active=True,
            search_revision=3,
            created_at=datetime(2026, 1, 1),
        ),
        owner_is_active=False,
    )
    indexer = RecordingReindexer()
    job = SearchReindexJob(
        SnapshotSource(item), indexer, policy=ReindexPolicy(throttle_seconds=0)
    )

    await job.reconcile_live()

    assert indexer.calls == ["live:3:False"]


@pytest.mark.asyncio
async def test_targeted_reindex_repairs_one_existing_product() -> None:
    product_id = uuid.uuid4()
    item = SearchSnapshotWithOwner(
        snapshot=ProductSearchSnapshot(
            product_id=product_id,
            user_id=uuid.uuid4(),
            name="Drill",
            description="",
            category="Tools",
            price=10.0,
            is_active=True,
            search_revision=5,
            created_at=datetime(2026, 1, 1),
        ),
        owner_is_active=True,
    )
    indexer = RecordingReindexer()
    job = SearchReindexJob(SnapshotSource(item), indexer)

    repaired = await job.reindex_product(product_id)

    assert repaired is True
    assert indexer.calls == ["live:5:True"]
