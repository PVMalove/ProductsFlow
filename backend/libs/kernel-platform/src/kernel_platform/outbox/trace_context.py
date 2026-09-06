"""W3C trace-context serialization for transactional Outbox rows."""

from __future__ import annotations

import json
from typing import Any

from opentelemetry import propagate
from opentelemetry.context import Context

_TRACE_CONTEXT_KEYS = frozenset({"traceparent", "tracestate"})


def w3c_carrier(carrier: dict[str, Any]) -> dict[str, str]:
    return {
        key: value
        for key, value in carrier.items()
        if key in _TRACE_CONTEXT_KEYS and isinstance(value, str)
    }


def serialize_trace_context() -> str | None:
    """Serialize the current W3C context for storage in an Outbox row."""
    carrier: dict[str, str] = {}
    propagate.inject(carrier)
    carrier = w3c_carrier(carrier)
    if "traceparent" not in carrier:
        return None
    return json.dumps(carrier, separators=(",", ":"), sort_keys=True)


def deserialize_trace_context(value: str | None) -> dict[str, str]:
    """Read a JSON carrier, accepting legacy plain ``traceparent`` values."""
    if not value:
        return {}
    try:
        decoded: Any = json.loads(value)
    except json.JSONDecodeError:
        return {"traceparent": value}

    if isinstance(decoded, str):
        return {"traceparent": decoded}
    if not isinstance(decoded, dict):
        return {}
    return w3c_carrier(decoded)


def extract_trace_context(value: str | None) -> Context:
    """Extract a stored W3C carrier as the parent for a publisher span."""
    return propagate.extract(deserialize_trace_context(value))


def inject_trace_context() -> dict[str, str]:
    """Inject the current W3C context into an AMQP-compatible carrier."""
    carrier: dict[str, str] = {}
    propagate.inject(carrier)
    return w3c_carrier(carrier)
