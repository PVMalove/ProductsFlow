"""Operator entry point for targeted rebuilds and nightly reconciliation."""

import argparse
import asyncio
import uuid

from sqlalchemy.ext.asyncio import async_sessionmaker, create_async_engine

from application.search_reindex import ReindexPolicy, SearchReindexJob
from core.settings import settings
from infrastructure.search.opensearch import OpenSearchProductSearch
from infrastructure.search.snapshot_source import PostgresProductSearchSnapshotSource


def _arguments() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Repair Catalog search projection")
    parser.add_argument(
        "--reconcile-only",
        action="store_true",
        help="repair the active alias from PostgreSQL without an alias switch",
    )
    parser.add_argument(
        "--product-id",
        type=uuid.UUID,
        help="repair one existing Product from PostgreSQL",
    )
    return parser.parse_args()


async def run(*, reconcile_only: bool, product_id: uuid.UUID | None = None) -> None:
    engine = create_async_engine(settings.catalog_database_url, pool_pre_ping=True)
    session_factory = async_sessionmaker(engine, expire_on_commit=False)
    indexer = OpenSearchProductSearch(
        base_url=settings.catalog_opensearch_url,
        index_name=settings.catalog_search_index_name,
    )
    job = SearchReindexJob(
        PostgresProductSearchSnapshotSource(session_factory),
        indexer,
        policy=ReindexPolicy(
            batch_size=settings.catalog_search_reindex_batch_size,
            throttle_seconds=settings.catalog_search_reconcile_throttle_seconds,
        ),
    )
    try:
        if product_id is not None:
            await job.reindex_product(product_id)
        elif reconcile_only:
            await job.reconcile_live()
        else:
            await job.rebuild()
    finally:
        await indexer.close()
        await engine.dispose()


def main() -> None:
    args = _arguments()
    asyncio.run(run(reconcile_only=args.reconcile_only, product_id=args.product_id))


if __name__ == "__main__":
    main()
