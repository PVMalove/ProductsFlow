"""core/psp.py::build_psp_client (issue #368, DoD п.2 / архитектурный бриф
D5) — fail-fast при APP_ENV=prod, MockPspAdapter в остальных окружениях."""

import pytest

from core.psp import build_psp_client
from core.settings import Settings
from infrastructure.psp.mock_psp_adapter import MockPspAdapter


def test_build_psp_client_returns_mock_adapter_outside_prod() -> None:
    settings = Settings(app_env="dev")

    client = build_psp_client(settings)

    assert isinstance(client, MockPspAdapter)


def test_build_psp_client_fails_fast_under_prod() -> None:
    settings = Settings(app_env="prod")

    with pytest.raises(RuntimeError):
        build_psp_client(settings)
