# ruff: noqa: E501
"""Prometheus-метрики публичного поиска (issue #293): epic #283 требует,
чтобы SLA поиска — задержка индексации, здоровье очереди catalog-search-
worker, латентность OpenSearch и эффективность Redis-кэша первой страницы —
были измеримы оператором платформы, а не только формально задокументированы.

`catalog-api` отдаёт эти метрики через `GET /metrics` (см. `api/main.py`),
`catalog-search-worker` — через отдельный `prometheus_client`-HTTP-сервер
(см. `api/search_worker.py`), т.к. это не FastAPI-процесс."""

import asyncio
import logging
import time
from collections.abc import AsyncIterator
from contextlib import asynccontextmanager
from datetime import UTC, datetime
from urllib.parse import quote

import httpx
from prometheus_client import Counter, Gauge, Histogram

logger = logging.getLogger(__name__)

SEARCH_CACHE_REQUESTS = Counter(
    "catalog_search_cache_requests_total",
    "Обращения к Redis-кэшу первой страницы публичного поиска.",
    ["result"],  # hit | miss
)

OPENSEARCH_REQUEST_LATENCY = Histogram(
    "catalog_opensearch_request_duration_seconds",
    "Латентность обращений catalog-service к OpenSearch.",
    ["operation"],  # search | index | delete
)

SEARCH_INDEXING_LAG = Histogram(
    "catalog_search_indexing_lag_seconds",
    "Время от outbox occurred_at (issue #291's `message.timestamp`) до "
    "успешной записи Product-снимка в OpenSearch.",
    buckets=(0.5, 1, 2, 5, 10, 20, 30, 60),
)

SEARCH_OLDEST_PENDING_EVENT_AGE = Gauge(
    "catalog_search_oldest_pending_event_age_seconds",
    "Возраст (occurred_at) самого старого события, которое "
    "catalog-search-worker сейчас активно обрабатывает.",
)

SEARCH_DLQ_DEPTH = Gauge(
    "catalog_search_dlq_depth",
    "Число сообщений в DLQ очереди catalog-search-worker.",
)


@asynccontextmanager
async def observe_opensearch_latency(operation: str) -> AsyncIterator[None]:
    """Замеряет длительность одного обращения к OpenSearch под меткой `operation`."""
    started = time.monotonic()
    try:
        yield
    finally:
        OPENSEARCH_REQUEST_LATENCY.labels(operation=operation).observe(
            time.monotonic() - started
        )


class PendingEventTracker:
    """Держит момент публикации (`occurred_at`) каждого сообщения, которое
    catalog-search-worker сейчас обрабатывает, и выставляет
    `SEARCH_OLDEST_PENDING_EVENT_AGE` по самому старому из них.

    RabbitMQ не даёт неразрушающе заглянуть в голову очереди, поэтому это —
    возраст сообщений в активной обработке, а не всей очереди целиком;
    воркер обрабатывает все доставленные брокером сообщения параллельно
    (в `consume()` нет ограничения prefetch), так что при реальном отставании
    это множество отражает и невыбранный бэклог тоже."""

    def __init__(self) -> None:
        self._occurred_at: dict[int, datetime] = {}
        self._lock = asyncio.Lock()

    async def mark_received(self, message_id: int, occurred_at: datetime) -> None:
        async with self._lock:
            self._occurred_at[message_id] = occurred_at
            self._refresh_gauge()

    async def mark_done(self, message_id: int) -> None:
        async with self._lock:
            self._occurred_at.pop(message_id, None)
            self._refresh_gauge()

    def _refresh_gauge(self) -> None:
        if not self._occurred_at:
            SEARCH_OLDEST_PENDING_EVENT_AGE.set(0)
            return
        oldest = min(self._occurred_at.values())
        age_seconds = (datetime.now(UTC) - oldest).total_seconds()
        SEARCH_OLDEST_PENDING_EVENT_AGE.set(max(age_seconds, 0.0))


async def poll_dlq_depth(
    *,
    management_url: str,
    username: str,
    password: str,
    queue_name: str,
    interval_seconds: float,
) -> None:
    """Периодически опрашивает RabbitMQ Management API за глубиной
    `{queue_name}.dlq` (issue #293 acceptance criterion 4) — то же соглашение
    об имени DLQ, что `kernel_platform.topology.declare_topology` уже
    использует для остальных consumer'ов платформы. Сама очередь появится,
    только когда issue #294 подключит dead-lettering к очереди поиска; пока
    её нет, `GET` отвечает 404, и метрика остаётся на нуле."""
    dlq_name = f"{queue_name}.dlq"
    url = f"{management_url}/api/queues/%2f/{quote(dlq_name, safe='')}"
    async with httpx.AsyncClient(auth=(username, password), timeout=5.0) as client:
        while True:
            try:
                response = await client.get(url)
                if response.status_code == 404:
                    SEARCH_DLQ_DEPTH.set(0)
                else:
                    response.raise_for_status()
                    SEARCH_DLQ_DEPTH.set(response.json()["messages"])
            except (
                httpx.HTTPError,
                KeyError,
                ValueError,
            ):
                logger.warning(
                    "catalog-search-worker: не удалось опросить глубину DLQ",
                    exc_info=True,
                )
            await asyncio.sleep(interval_seconds)
