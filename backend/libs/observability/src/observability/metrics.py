"""Common, low-cardinality Prometheus metrics for the HTTP APIs."""

from collections.abc import Callable

from prometheus_client import REGISTRY, CollectorRegistry, Counter, Gauge
from prometheus_fastapi_instrumentator import Instrumentator
from prometheus_fastapi_instrumentator.metrics import default
from starlette.applications import Starlette
from starlette.middleware.base import BaseHTTPMiddleware, RequestResponseEndpoint
from starlette.requests import Request
from starlette.responses import Response
from starlette.types import ASGIApp

_METRICS_ENDPOINT = "/metrics"


class _RequestsInProgressMiddleware(BaseHTTPMiddleware):
    """Tracks concurrency (requests piling up), which `default()`'s
    completed-request counters/histograms can't show on their own — a slow
    downstream dependency looks the same as low traffic in the RPS graph
    until you can see requests actually queuing up here.

    A separate `BaseHTTPMiddleware`, not `Instrumentator`'s own
    `should_instrument_requests_inprogress` flag: that feature builds its
    Gauge with no `namespace`/`subsystem`/`registry`, so it lands on
    prometheus_client's global default registry under the bare name
    `http_requests_inprogress` — colliding (`DuplicateTimeseries`) the
    moment a second service or a second test in the same process tries the
    same thing, and losing the per-service label everywhere else already has.
    """

    def __init__(self, app: ASGIApp, gauge: Gauge) -> None:
        super().__init__(app)
        self._gauge = gauge

    async def dispatch(
        self, request: Request, call_next: RequestResponseEndpoint
    ) -> Response:
        if request.url.path == _METRICS_ENDPOINT:
            return await call_next(request)
        self._gauge.inc()
        try:
            return await call_next(request)
        finally:
            self._gauge.dec()


def _metric_subsystem(service_name: str) -> str:
    return "".join(
        character if character.isalnum() else "_" for character in service_name
    ).strip("_")


def register_http_metrics(
    app: Starlette,
    *,
    service_name: str,
    registry: CollectorRegistry = REGISTRY,
) -> None:
    """Register normalized HTTP metrics and the internal scrape endpoint.

    The instrumentator's route resolver emits the FastAPI route template in
    the ``handler`` label. The service name is a bounded label and is also
    part of the metric subsystem so separate API processes can be scraped
    into one Prometheus instance without ambiguous metric names.
    """
    if getattr(app.state, "_http_metrics_registered", False):
        return

    subsystem = _metric_subsystem(service_name)
    instrumentator = Instrumentator(
        should_group_status_codes=False,
        should_ignore_untemplated=True,
        excluded_handlers=[_METRICS_ENDPOINT],
        registry=registry,
    )
    instrumentator.add(
        default(
            metric_namespace="productsflow",
            metric_subsystem=subsystem,
            registry=registry,
            custom_labels={"service": service_name},
        )
    )
    instrumentator.instrument(
        app,
        metric_namespace="productsflow",
        metric_subsystem=subsystem,
    ).expose(app, endpoint=_METRICS_ENDPOINT, include_in_schema=False)

    inprogress = Gauge(
        "http_requests_inprogress",
        "Number of HTTP requests currently being processed.",
        namespace="productsflow",
        subsystem=subsystem,
        registry=registry,
    )
    app.add_middleware(_RequestsInProgressMiddleware, gauge=inprogress)
    app.state._http_metrics_registered = True


def register_exception_metrics(
    service_name: str,
    *,
    registry: CollectorRegistry = REGISTRY,
) -> Callable[[Exception], None]:
    """Build a counter of unhandled (500) exceptions by Python type, and
    return the recording callback for `kernel_platform`'s
    `register_error_handlers(..., on_unhandled_exception=...)` — kept here,
    not in kernel_platform, so that generic error-handling code never gains a
    prometheus_client dependency."""
    counter = Counter(
        "http_exceptions_total",
        "Unhandled exceptions raised while processing an HTTP request, by type.",
        labelnames=["exception_type", "service"],
        namespace="productsflow",
        subsystem=_metric_subsystem(service_name),
        registry=registry,
    )

    def record(exc: Exception) -> None:
        counter.labels(exception_type=type(exc).__name__, service=service_name).inc()

    return record
