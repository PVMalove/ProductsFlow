from prometheus_client import CollectorRegistry
from sqlalchemy import text
from sqlalchemy.exc import OperationalError
from sqlalchemy.ext.asyncio import async_sessionmaker, create_async_engine
from starlette.applications import Starlette

from observability.db_metrics import instrument_sqlalchemy_sessionmaker


async def test_records_a_query_duration_observation_per_statement() -> None:
    app = Starlette()
    sessionmaker = async_sessionmaker(
        create_async_engine("sqlite+aiosqlite:///:memory:"), expire_on_commit=False
    )
    registry = CollectorRegistry()
    instrument_sqlalchemy_sessionmaker(
        app, sessionmaker, service_name="catalog-service", registry=registry
    )

    async with sessionmaker() as session:
        await session.execute(text("SELECT 1"))
        await session.execute(text("SELECT 2"))

    sample = registry.get_sample_value(
        "productsflow_catalog_service_db_query_duration_seconds_count",
        {"service": "catalog-service"},
    )
    assert sample == 2


async def test_does_not_observe_anything_before_a_statement_runs() -> None:
    app = Starlette()
    sessionmaker = async_sessionmaker(
        create_async_engine("sqlite+aiosqlite:///:memory:"), expire_on_commit=False
    )
    registry = CollectorRegistry()
    instrument_sqlalchemy_sessionmaker(
        app, sessionmaker, service_name="support-service", registry=registry
    )

    sample = registry.get_sample_value(
        "productsflow_support_service_db_query_duration_seconds_count",
        {"service": "support-service"},
    )
    assert sample is None


async def test_exposes_pool_snapshot_at_scrape_time() -> None:
    app = Starlette()
    sessionmaker = async_sessionmaker(
        create_async_engine("sqlite+aiosqlite:///:memory:"), expire_on_commit=False
    )
    registry = CollectorRegistry()
    instrument_sqlalchemy_sessionmaker(
        app, sessionmaker, service_name="catalog-service", registry=registry
    )

    # SQLite's StaticPool has no QueuePool counters. The metric is still
    # exported with a safe, explicit zero rather than disappearing.
    assert (
        registry.get_sample_value(
            "productsflow_catalog_service_db_pool_connections",
            {"service": "catalog-service", "state": "checked_out"},
        )
        == 0
    )


async def test_counts_failed_statement_by_exception_type() -> None:
    app = Starlette()
    sessionmaker = async_sessionmaker(
        create_async_engine("sqlite+aiosqlite:///:memory:"), expire_on_commit=False
    )
    registry = CollectorRegistry()
    instrument_sqlalchemy_sessionmaker(
        app, sessionmaker, service_name="support-service", registry=registry
    )

    async with sessionmaker() as session:
        try:
            await session.execute(text("SELECT * FROM absent_table"))
        except OperationalError:
            pass

    assert (
        registry.get_sample_value(
            "productsflow_support_service_db_query_errors_total",
            {"exception_type": "OperationalError", "service": "support-service"},
        )
        == 1
    )


async def test_a_second_lifespan_entry_does_not_re_register_the_histogram() -> None:
    """Mirrors register_http_metrics's own idempotency test — `lifespan`
    builds a fresh sessionmaker per entry, but repeated `TestClient(app)`
    entries in unit tests share one module-level `app`/`REGISTRY`."""
    app = Starlette()
    registry = CollectorRegistry()

    first_sessionmaker = async_sessionmaker(
        create_async_engine("sqlite+aiosqlite:///:memory:"), expire_on_commit=False
    )
    instrument_sqlalchemy_sessionmaker(
        app, first_sessionmaker, service_name="identity-service", registry=registry
    )

    second_sessionmaker = async_sessionmaker(
        create_async_engine("sqlite+aiosqlite:///:memory:"), expire_on_commit=False
    )
    instrument_sqlalchemy_sessionmaker(
        app, second_sessionmaker, service_name="identity-service", registry=registry
    )
