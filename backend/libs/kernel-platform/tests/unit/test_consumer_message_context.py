# ruff: noqa: E501
from aio_pika.abc import HeadersType
from opentelemetry import trace

from kernel_platform.consumer import _extract_message_context


def test_extract_message_context_is_empty_without_headers() -> None:
    context = _extract_message_context({})

    assert trace.get_current_span(context) is trace.INVALID_SPAN


def test_extract_message_context_falls_back_on_malformed_traceparent() -> None:
    headers: HeadersType = {"traceparent": "not-a-valid-traceparent"}

    context = _extract_message_context(headers)

    assert trace.get_current_span(context) is trace.INVALID_SPAN


def test_extract_message_context_ignores_non_string_header_values() -> None:
    # `x-death` — реальный AMQP-заголовок с list-значением; убеждаемся, что
    # он просто отфильтровывается, а не ломает извлечение.
    headers: HeadersType = {"traceparent": None, "x-death": [{"queue": "q"}]}

    context = _extract_message_context(headers)

    assert trace.get_current_span(context) is trace.INVALID_SPAN


def test_extract_message_context_extracts_valid_traceparent() -> None:
    headers: HeadersType = {
        "traceparent": "00-4bf92f3577b34da6a3ce929d0e0e4736-00f067aa0ba902b7-01"
    }

    context = _extract_message_context(headers)

    span_context = trace.get_current_span(context).get_span_context()
    assert (
        span_context.trace_id.to_bytes(16, "big").hex()
        == "4bf92f3577b34da6a3ce929d0e0e4736"
    )
    assert span_context.span_id.to_bytes(8, "big").hex() == "00f067aa0ba902b7"
