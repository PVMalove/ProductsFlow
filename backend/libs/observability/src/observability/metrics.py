"""Common, low-cardinality Prometheus metrics for the HTTP APIs."""

from prometheus_client import REGISTRY, CollectorRegistry
from prometheus_fastapi_instrumentator import Instrumentator
from prometheus_fastapi_instrumentator.metrics import default
from starlette.applications import Starlette

_METRICS_ENDPOINT = "/metrics"


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
    app.state._http_metrics_registered = True
