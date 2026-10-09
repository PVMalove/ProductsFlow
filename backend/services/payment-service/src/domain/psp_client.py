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


class PspCaptureLookupOutcome(enum.StrEnum):
    """Окончательный ответ PSP на сверку capture по idempotency-ключу (issue
    #374): операция либо записана провайдером, либо её отсутствие
    подтверждено."""

    CAPTURED = "captured"
    NOT_FOUND = "not_found"


class UnknownPspScenarioTokenError(Exception):
    """Поднимается адаптером, если `payment_method_token` не входит в
    распознанный сценарный словарь (архитектурный бриф D4) — application-слой
    ловит её и превращает в `PaymentErrors.unknown_test_scenario_token()`."""


class PspClient(Protocol):
    """Контракт платёжного провайдера. `capture` вызывается только для
    авторизации, уже находящейся в статусе `AUTHORIZED` — вызывающий отвечает
    за то, чтобы не переспрашивать провайдера повторно по тому же
    idempotency-ключу (application-слой, не порт).

    `capture` получает idempotency-ключ (issue #374): сверка через
    `lookup_capture` по ключу осмысленна, только если провайдер этот ключ
    получил, и только по нему реальный PSP может дедуплицировать повтор
    после отката inbox-транзакции."""

    async def authorize(
        self, payment_method_token: str, amount: int
    ) -> PspAuthorizeOutcome: ...

    async def capture(
        self, payment_method_token: str, idempotency_key: str
    ) -> PspCaptureOutcome: ...

    async def lookup_capture(
        self, payment_method_token: str, idempotency_key: str
    ) -> PspCaptureLookupOutcome: ...
