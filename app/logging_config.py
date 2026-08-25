import logging
import sys


class ColorFormatter(logging.Formatter):
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


def configure_logging() -> None:
    app_logger = logging.getLogger("app")
    app_logger.setLevel(logging.DEBUG)
    app_logger.propagate = False
    if app_logger.handlers:
        return

    console_handler = logging.StreamHandler(sys.stdout)
    console_handler.setFormatter(
        ColorFormatter("%(asctime)s %(levelname)s %(name)s: %(message)s")
    )
    app_logger.addHandler(console_handler)
