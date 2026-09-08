"""SQL statement duration metric, shared by API processes.

Hooks the sync engine underlying each service's `async_sessionmaker` —
`before_cursor_execute`/`after_cursor_execute` are SQLAlchemy Core events and
only fire on the sync engine, even for the async dialect (ADR: async support
is a thin wrapper around the sync engine via greenlet).
"""

import time
from collections.abc import Callable

from prometheus_client import REGISTRY, CollectorRegistry, Counter, Gauge, Histogram
from sqlalchemy import event
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker
from starlette.applications import Starlette

from observability.metrics import _metric_subsystem

_QUERY_START_ATTR = "_productsflow_query_start_time"


def instrument_sqlalchemy_sessionmaker(
    app: Starlette,
    sessionmaker: async_sessionmaker[AsyncSession],
    *,
    service_name: str,
    registry: CollectorRegistry = REGISTRY,
) -> None:
    """Times every statement executed through `sessionmaker`'s engine into a
    Prometheus histogram (`productsflow_<service>_db_query_duration_seconds`).

    Guarded like `register_http_metrics`: `lifespan` builds a fresh engine
    (and thus a fresh call to this function) on every startup, including
    every `TestClient(app)` entry in unit tests sharing the same module-level
    `app` — without the flag, the second entry re-registers the histogram on
    the same process-wide `REGISTRY` and raises."""
    if getattr(app.state, "_db_metrics_registered", False):
        return

    engine = sessionmaker.kw["bind"].sync_engine

    histogram = Histogram(
        "db_query_duration_seconds",
        "Duration of SQL statements executed through this engine.",
        labelnames=["service"],
        namespace="productsflow",
        subsystem=_metric_subsystem(service_name),
        registry=registry,
    )
    query_errors = Counter(
        "db_query_errors_total",
        "SQL statement failures observed through this engine.",
        labelnames=["exception_type", "service"],
        namespace="productsflow",
        subsystem=_metric_subsystem(service_name),
        registry=registry,
    )
    pool_connections = Gauge(
        "db_pool_connections",
        "Current SQLAlchemy connection-pool capacity and checked-out connections.",
        labelnames=["service", "state"],
        namespace="productsflow",
        subsystem=_metric_subsystem(service_name),
        registry=registry,
    )

    pool = engine.pool

    def _pool_stat(method_name: str) -> float:
        method = getattr(pool, method_name, None)
        return float(method()) if callable(method) else 0.0

    def _pool_stat_collector(method_name: str) -> Callable[[], float]:
        def _collect() -> float:
            return _pool_stat(method_name)

        return _collect

    # `set_function` is evaluated by Prometheus at scrape time.  It avoids a
    # stale value after the last SQL statement and gracefully reports zero for
    # pools such as SQLite's StaticPool that do not expose QueuePool counters.
    for state, method_name in (
        ("size", "size"),
        ("checked_out", "checkedout"),
        ("overflow", "overflow"),
    ):
        pool_connections.labels(service=service_name, state=state).set_function(
            _pool_stat_collector(method_name)
        )

    @event.listens_for(engine, "before_cursor_execute")
    def _before_cursor_execute(
        _conn, _cursor, _statement, _parameters, context, _executemany
    ) -> None:
        setattr(context, _QUERY_START_ATTR, time.perf_counter())

    @event.listens_for(engine, "after_cursor_execute")
    def _after_cursor_execute(
        _conn, _cursor, _statement, _parameters, context, _executemany
    ) -> None:
        started_at = getattr(context, _QUERY_START_ATTR, None)
        if started_at is not None:
            histogram.labels(service=service_name).observe(
                time.perf_counter() - started_at
            )

    @event.listens_for(engine, "handle_error")
    def _handle_error(exception_context) -> None:
        exception = exception_context.original_exception
        query_errors.labels(
            exception_type=type(exception).__name__, service=service_name
        ).inc()

    app.state._db_metrics_registered = True
