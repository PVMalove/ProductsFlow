# ruff: noqa: E501
import json
import logging
from datetime import UTC, datetime
from typing import Any

from observability.context import (
    actor_id_var,
    request_id_var,
    span_id_var,
    trace_id_var,
)

_DEV_FMT = "%(asctime)s %(levelname)s %(name)s: %(message)s"


class JsonFormatter(logging.Formatter):
    """Дефолт/prod-форматтер : все 13 полей TD Фазы 8 present в
    каждой строке. `trace_id`/`span_id` — `null`-ключи, пока их не выставит
    OTEL-инструментация Фазы 10; `method`/`path`/`status_code`/`duration_ms`
    — `null` вне access-log-записи, которую пишет `RequestContextMiddleware`
    через `extra`."""

    def __init__(self, service: str) -> None:
        """Инициализирует форматтер, прибивая гвоздями имя сервиса.

        Args:
            service (str): Имя микросервиса (например, "catalog-service"), которое будет подмешано в каждый лог-ивент."""
        super().__init__()
        self._service = service

    def format(self, record: logging.LogRecord) -> str:
        """Сериализует лог-запись в JSON-строку с фиксированным набором полей для продакшена.

        Алгоритм:
        1. Конвертит таймстемп в ISO 8601 UTC.
        2. Тянет `request_id`, `trace_id`, `span_id`, `actor_id` из `contextvars` (в локальном скоупе корутины/потока).
        3. Фоллбэчит кастомные атрибуты (`method`, `path`, `status_code`, `duration_ms`) в `None`, если их не заинжектили через `extra` в вызове логгера.
        4. Дампит дикт в JSON, отключая `ensure_ascii` для нативного UTF-8.

        Args:
            record (logging.LogRecord): Сырая запись лога. Ожидается, что может содержать кастомные аттрибуты.

        Returns:
            str: Готовая к отправке в агрегатор (ELK/stdout) JSON-строка."""
        payload: dict[str, Any] = {
            "timestamp": datetime.fromtimestamp(record.created, tz=UTC).isoformat(),
            "level": record.levelname,
            "logger": record.name,
            "message": record.getMessage(),
            "service": self._service,
            "request_id": request_id_var.get(),
            "trace_id": trace_id_var.get(),
            "span_id": span_id_var.get(),
            "actor_id": actor_id_var.get(),
            "method": getattr(record, "method", None),
            "path": getattr(record, "path", None),
            "status_code": getattr(record, "status_code", None),
            "duration_ms": getattr(record, "duration_ms", None),
        }
        return json.dumps(payload, ensure_ascii=False)


class ColorFormatter(logging.Formatter):
    """Перенос `app/logging_config.py` монолита без изменения логики
    раскраски  — только смена владельца пакета."""

    _COLORS = {
        logging.DEBUG: "\x1b[36m",
        logging.INFO: "\x1b[32m",
        logging.WARNING: "\x1b[33m",
        logging.ERROR: "\x1b[31m",
        logging.CRITICAL: "\x1b[35m",
    }
    _RESET = "\x1b[0m"

    def format(self, record: logging.LogRecord) -> str:
        """Форматирует лог-запись с ANSI-цветами для локальной разработки.

        Красит всю строку целиком на основе `levelno`. Если уровень не замаплен в `_COLORS`, откатывается к стандартному цвету терминала (`_RESET`).

        Args:
            record (logging.LogRecord): Входящая запись лога.

        Returns:
            str: Цветная строка лога, обрамленная ANSI escape-кодами."""
        message = super().format(record)
        color = self._COLORS.get(record.levelno, self._RESET)
        return f"{color}{message}{self._RESET}"


def select_formatter(app_env: str, service: str) -> logging.Formatter:
    """Фабрика для выбора лог-форматтера в зависимости от окружения.

    Интуиция: локально нам нужны цветные логи в stdout для дебага глазками (`ColorFormatter`), а на проде/стейдже — структурированный JSON для агрегаторов (`JsonFormatter`).

    Args:
        app_env (str): Окружение, обычно тянется из конфига (например, "dev", "prod").
        service (str): Имя текущего сервиса для инжекта в JSON.

    Returns:
        logging.Formatter: Сконфигурированный инстанс форматтера."""
    if app_env == "dev":
        return ColorFormatter(_DEV_FMT)
    return JsonFormatter(service)
