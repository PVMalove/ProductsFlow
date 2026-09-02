# ruff: noqa: E501
from contextvars import ContextVar

request_id_var: ContextVar[str | None] = ContextVar("request_id_var", default=None)
actor_id_var: ContextVar[int | str | None] = ContextVar("actor_id_var", default=None)

# Зарезервированы под OTEL-инструментацию (Фаза 10) — здесь их
# никто не выставляет.
trace_id_var: ContextVar[str | None] = ContextVar("trace_id_var", default=None)
span_id_var: ContextVar[str | None] = ContextVar("span_id_var", default=None)
