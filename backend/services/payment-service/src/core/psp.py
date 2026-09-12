"""Fail-fast гейт для `MockPspAdapter` (issue #368, архитектурный бриф D5) —
зеркалит идиом `identity-service/core/secrets.py::validate_prod_key`: под
`APP_ENV=prod` сервис не должен обслуживать трафик, пока не появится
настоящий `PspClient`-адаптер (реального PSP не существует, вне скоупа #368)."""

from core.settings import Settings
from domain.psp_client import PspClient
from infrastructure.psp.mock_psp_adapter import MockPspAdapter


def build_psp_client(settings: Settings) -> PspClient:
    if settings.app_env == "prod":
        raise RuntimeError(
            "MockPspAdapter недоступен при APP_ENV=prod — реальный "
            "PspClient-адаптер ещё не реализован (issue #368)"
        )
    return MockPspAdapter()
