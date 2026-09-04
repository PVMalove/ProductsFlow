import logging
import sys

from observability.formatters import select_formatter

_SERVICE_NAME = "identity-service"


def configure_logging(app_env: str, logger: logging.Logger | None = None) -> None:
    """Переключает формат логов identity-api через select_formatter из
    kernel-platform (ADR 0005, issue #120). По умолчанию ставится на
    root-логгер — под этот формат попадают и access-log строки
    RequestContextMiddleware (логгер observability.middleware),
    и собственные логи сервиса."""
    target = logger if logger is not None else logging.getLogger()
    if target.handlers:
        return
    target.setLevel(logging.INFO)
    handler = logging.StreamHandler(sys.stdout)
    handler.setFormatter(select_formatter(app_env, _SERVICE_NAME))
    target.addHandler(handler)
