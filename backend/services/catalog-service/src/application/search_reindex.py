"""Zero-downtime rebuild orchestration for the Catalog search read model."""

import asyncio
import uuid
from dataclasses import dataclass

from application.ports import ProductSearchReindexer, ProductSearchSnapshotSource


@dataclass(frozen=True)
class ReindexPolicy:
    batch_size: int = 500
    throttle_seconds: float = 0.05


class SearchReindexJob:
    """Copies PostgreSQL state to a versioned index while events are mirrored.

    A second, throttled pass reconciles mutations which raced the first bulk
    snapshot.  The writer keeps mirroring AMQP events into the target until
    the alias transaction completes, closing the final hand-off window.
    """

    def __init__(
        self,
        source: ProductSearchSnapshotSource,
        indexer: ProductSearchReindexer,
        *,
        policy: ReindexPolicy = ReindexPolicy(),
    ) -> None:
        self._source = source
        self._indexer = indexer
        self._policy = policy

    async def rebuild(self) -> None:
        await self._indexer.begin_reindex()
        try:
            await self.reconcile()
            await self.reconcile()
            await self._indexer.complete_reindex()
        except Exception:
            # The old alias deliberately remains live.  A later operator run
            # creates a new target rather than exposing a partial index.
            raise

    async def reconcile(self) -> None:
        async for batch in self._source.stream_batches(
            batch_size=self._policy.batch_size
        ):
            for item in batch:
                await self._indexer.index_rebuild(
                    item.snapshot, owner_is_active=item.owner_is_active
                )
            if batch and self._policy.throttle_seconds:
                await asyncio.sleep(self._policy.throttle_seconds)

    async def reconcile_live(self) -> None:
        """Throttled repair of the current alias, suitable for nightly use."""
        async for batch in self._source.stream_batches(
            batch_size=self._policy.batch_size
        ):
            for item in batch:
                await self._indexer.index(
                    item.snapshot, owner_is_active=item.owner_is_active
                )
            if batch and self._policy.throttle_seconds:
                await asyncio.sleep(self._policy.throttle_seconds)

    async def reindex_product(self, product_id: uuid.UUID) -> bool:
        """Repair one extant Product after a poison-event remediation.

        Deleted Products are intentionally not rediscovered from PostgreSQL;
        replay their retained minimal tombstone from the DLQ instead.
        """
        item = await self._source.get(product_id)
        if item is None:
            return False
        await self._indexer.index(item.snapshot, owner_is_active=item.owner_is_active)
        return True
