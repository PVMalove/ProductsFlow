# ruff: noqa: E501
import json
import logging

from observability.context import (
    actor_id_var,
    request_id_var,
    span_id_var,
    trace_id_var,
)
from observability.formatters import JsonFormatter

ALL_FIELDS = {
    "timestamp",
    "level",
    "logger",
    "message",
    "service",
    "request_id",
    "trace_id",
    "span_id",
    "actor_id",
    "method",
    "path",
    "status_code",
    "duration_ms",
}


def _make_record(message: str = "hello") -> logging.LogRecord:
    return logging.LogRecord(
        name="observability.test",
        level=logging.INFO,
        pathname=__file__,
        lineno=1,
        msg=message,
        args=(),
        exc_info=None,
    )


def test_emits_all_13_fields() -> None:
    formatter = JsonFormatter(service="identity-service")

    payload = json.loads(formatter.format(_make_record()))

    assert set(payload) == ALL_FIELDS


def test_trace_and_span_are_null_keys_when_contextvars_unset() -> None:
    formatter = JsonFormatter(service="identity-service")

    payload = json.loads(formatter.format(_make_record()))

    assert "trace_id" in payload
    assert payload["trace_id"] is None
    assert "span_id" in payload
    assert payload["span_id"] is None


def test_reads_request_and_actor_id_from_contextvars() -> None:
    formatter = JsonFormatter(service="identity-service")
    request_id_token = request_id_var.set("req-1")
    actor_id_token = actor_id_var.set(42)
    try:
        payload = json.loads(formatter.format(_make_record()))
    finally:
        request_id_var.reset(request_id_token)
        actor_id_var.reset(actor_id_token)

    assert payload["request_id"] == "req-1"
    assert payload["actor_id"] == 42


def test_reads_trace_and_span_when_set() -> None:
    formatter = JsonFormatter(service="identity-service")
    trace_id_token = trace_id_var.set("trace-1")
    span_id_token = span_id_var.set("span-1")
    try:
        payload = json.loads(formatter.format(_make_record()))
    finally:
        trace_id_var.reset(trace_id_token)
        span_id_var.reset(span_id_token)

    assert payload["trace_id"] == "trace-1"
    assert payload["span_id"] == "span-1"


def test_access_log_fields_come_from_record_extra() -> None:
    formatter = JsonFormatter(service="identity-service")
    record = _make_record("access")
    record.method = "GET"
    record.path = "/api/v1/users/me"
    record.status_code = 200
    record.duration_ms = 12.5

    payload = json.loads(formatter.format(record))

    assert payload["method"] == "GET"
    assert payload["path"] == "/api/v1/users/me"
    assert payload["status_code"] == 200
    assert payload["duration_ms"] == 12.5


def test_access_log_fields_are_null_keys_outside_access_log_records() -> None:
    formatter = JsonFormatter(service="identity-service")

    payload = json.loads(formatter.format(_make_record()))

    assert payload["method"] is None
    assert payload["path"] is None
    assert payload["status_code"] is None
    assert payload["duration_ms"] is None


def test_message_and_service_and_level_and_logger() -> None:
    formatter = JsonFormatter(service="identity-service")

    payload = json.loads(formatter.format(_make_record("something happened")))

    assert payload["message"] == "something happened"
    assert payload["service"] == "identity-service"
    assert payload["level"] == "INFO"
    assert payload["logger"] == "observability.test"
