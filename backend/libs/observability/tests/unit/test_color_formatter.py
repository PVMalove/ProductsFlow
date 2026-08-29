import logging

from observability.formatters import ColorFormatter


def _make_record(level: int, message: str) -> logging.LogRecord:
    return logging.LogRecord(
        name="observability.test",
        level=level,
        pathname=__file__,
        lineno=1,
        msg=message,
        args=(),
        exc_info=None,
    )


def test_output_contains_the_message_and_level_name() -> None:
    formatter = ColorFormatter("%(levelname)s %(message)s")

    output = formatter.format(_make_record(logging.INFO, "hello world"))

    assert "hello world" in output
    assert "INFO" in output


def test_output_is_wrapped_in_ansi_color_codes() -> None:
    formatter = ColorFormatter("%(message)s")

    output = formatter.format(_make_record(logging.ERROR, "boom"))

    assert output.startswith("\033[31m")
    assert output.endswith("\033[0m")
