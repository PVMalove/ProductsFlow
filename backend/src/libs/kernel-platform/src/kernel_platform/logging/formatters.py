import json
import logging
from datetime import UTC, datetime
from typing import Any

from kernel_platform.logging.context import (
    actor_id_var,
    request_id_var,
    span_id_var,
    trace_id_var,
)

_DEV_FMT = "%(asctime)s %(levelname)s %(name)s: %(message)s"


class JsonFormatter(logging.Formatter):
    """Дефолт/prod-форматтер (ADR 0016): все 13 полей TD Фазы 8 present в
    каждой строке. `trace_id`/`span_id` — `null`-ключи, пока их не выставит
    OTEL-инструментация Фазы 10; `method`/`path`/`status_code`/`duration_ms`
    — `null` вне access-log-записи, которую пишет `RequestContextMiddleware`
    через `extra`."""

    def __init__(self, service: str) -> None:
        super().__init__()
        self._service = service

    def format(self, record: logging.LogRecord) -> str:
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
    раскраски (ADR 0016) — только смена владельца пакета."""

    _COLORS = {
        logging.DEBUG: "\033[36m",
        logging.INFO: "\033[32m",
        logging.WARNING: "\033[33m",
        logging.ERROR: "\033[31m",
        logging.CRITICAL: "\033[35m",
    }
    _RESET = "\033[0m"

    def format(self, record: logging.LogRecord) -> str:
        message = super().format(record)
        color = self._COLORS.get(record.levelno, self._RESET)
        return f"{color}{message}{self._RESET}"


def select_formatter(app_env: str, service: str) -> logging.Formatter:
    """Не завязана на shared-settings (их в kernel-platform нет) — каждый
    сервис вызывает её из своих настроек (`settings.app_env`)."""
    if app_env == "dev":
        return ColorFormatter(_DEV_FMT)
    return JsonFormatter(service)
