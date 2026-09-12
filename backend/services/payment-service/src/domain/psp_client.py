"""Domain-порт детерминированного Test PSP (ADR 0006, issue #368). Единственная
реализация сегодня — `infrastructure/psp/mock_psp_adapter.py::MockPspAdapter`,
допустимая только при `APP_ENV != "prod"` (архитектурный бриф D5)."""

import enum
from typing import Protocol


class PspAuthorizeOutcome(enum.StrEnum):
    SUCCESS = "success"
    DECLINE = "decline"
    TIMEOUT = "timeout"


class PspCaptureOutcome(enum.StrEnum):
    CAPTURED = "captured"
    UNKNOWN = "unknown"


class UnknownPspScenarioTokenError(Exception):
    """Поднимается адаптером, если `payment_method_token` не входит в
    распознанный сценарный словарь (архитектурный бриф D4) — application-слой
    ловит её и превращает в `PaymentErrors.unknown_test_scenario_token()`."""


class PspClient(Protocol):
    """Контракт платёжного провайдера. `capture` вызывается только для
    авторизации, уже находящейся в статусе `AUTHORIZED` — вызывающий отвечает
    за то, чтобы не переспрашивать провайдера повторно по тому же
    idempotency-ключу (application-слой, не порт)."""

    async def authorize(
        self, payment_method_token: str, amount: int
    ) -> PspAuthorizeOutcome: ...

    async def capture(self, payment_method_token: str) -> PspCaptureOutcome: ...
