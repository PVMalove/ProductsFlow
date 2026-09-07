import logging

from observability.formatters import configure_logging as _configure_logging

_SERVICE_NAME = "identity-service"


def configure_logging(app_env: str, logger: logging.Logger | None = None) -> None:
    """Переключает формат логов identity-api через select_formatter из
    kernel-platform (ADR 0005, issue #120). По умолчанию ставится на
    root-логгер — под этот формат попадают и access-log строки
    RequestContextMiddleware (логгер observability.middleware),
    и собственные логи сервиса."""
    _configure_logging(app_env, _SERVICE_NAME, logger=logger)
