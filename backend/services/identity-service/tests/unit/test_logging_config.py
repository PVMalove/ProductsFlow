import logging
from collections.abc import Iterator

import pytest
from observability.formatters import ColorFormatter, JsonFormatter

from core.logging_config import configure_logging


@pytest.fixture
def scratch_logger() -> Iterator[logging.Logger]:
    logger = logging.getLogger("test_configure_logging_scratch")
    yield logger
    logger.handlers.clear()


def test_dev_app_env_attaches_a_color_formatter(scratch_logger: logging.Logger) -> None:
    configure_logging("dev", logger=scratch_logger)

    assert isinstance(scratch_logger.handlers[0].formatter, ColorFormatter)


def test_non_dev_app_env_attaches_a_json_formatter(
    scratch_logger: logging.Logger,
) -> None:
    configure_logging("prod", logger=scratch_logger)

    assert isinstance(scratch_logger.handlers[0].formatter, JsonFormatter)


def test_is_idempotent_and_does_not_stack_handlers(
    scratch_logger: logging.Logger,
) -> None:
    configure_logging("dev", logger=scratch_logger)
    configure_logging("dev", logger=scratch_logger)

    assert len(scratch_logger.handlers) == 1
