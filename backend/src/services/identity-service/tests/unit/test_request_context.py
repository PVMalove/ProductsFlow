import logging

import pytest
from fastapi.testclient import TestClient
from identity_service.infrastructure.security.tokens import create_access_token
from identity_service.main import app
from kernel_platform.logging.context import actor_id_var

pytestmark = pytest.mark.usefixtures("configured_key_path")

_MIDDLEWARE_LOGGER = "kernel_platform.logging.middleware"


class _ActorIdCapturingHandler(logging.Handler):
    """Читает actor_id_var в момент emit() — тот же момент, когда его читает
    JsonFormatter в проде (middleware пишет access-log до сброса ContextVar,
    см. RequestContextMiddleware.dispatch's finally)."""

    def __init__(self) -> None:
        super().__init__()
        self.captured: list[int | None] = []

    def emit(self, record: logging.LogRecord) -> None:
        # Тот же логгер пишет и WARNING на невалидный bearer (middleware.py's
        # _set_actor_id) — нас интересует только access-log строка, у неё
        # есть extra "path".
        if hasattr(record, "path"):
            self.captured.append(actor_id_var.get())


def test_valid_bearer_sets_actor_id_and_writes_one_access_log_line(
    caplog: pytest.LogCaptureFixture,
) -> None:
    token = create_access_token(sub=42)
    handler = _ActorIdCapturingHandler()
    logger = logging.getLogger(_MIDDLEWARE_LOGGER)
    logger.addHandler(handler)
    try:
        with caplog.at_level(logging.INFO, logger=_MIDDLEWARE_LOGGER):
            with TestClient(app) as client:
                response = client.get(
                    "/.well-known/jwks.json",
                    headers={"Authorization": f"Bearer {token}"},
                )
    finally:
        logger.removeHandler(handler)

    assert response.status_code == 200
    assert response.headers["x-request-id"]

    records = [r for r in caplog.records if r.name == _MIDDLEWARE_LOGGER]
    assert len(records) == 1
    assert getattr(records[0], "method") == "GET"
    assert getattr(records[0], "path") == "/.well-known/jwks.json"
    assert getattr(records[0], "status_code") == 200

    assert handler.captured == [42]


@pytest.mark.parametrize(
    "headers",
    [{}, {"Authorization": "Bearer not-a-jwt-at-all"}],
    ids=["no_bearer", "invalid_bearer"],
)
def test_missing_or_invalid_bearer_does_not_block_and_logs_actor_id_none(
    headers: dict[str, str],
    caplog: pytest.LogCaptureFixture,
) -> None:
    handler = _ActorIdCapturingHandler()
    logger = logging.getLogger(_MIDDLEWARE_LOGGER)
    logger.addHandler(handler)
    try:
        with caplog.at_level(logging.INFO, logger=_MIDDLEWARE_LOGGER):
            with TestClient(app) as client:
                response = client.get("/.well-known/jwks.json", headers=headers)
    finally:
        logger.removeHandler(handler)

    assert response.status_code == 200
    assert handler.captured == [None]
