"""Фейковый PspClient для юнит-тестов application handler'ов (issue #368) —
считает вызовы, чтобы тесты могли утверждать «PSP не переспрашивается» при
повторном idempotency-ключе."""

from domain.psp_client import (
    PspAuthorizeOutcome,
    PspCaptureLookupOutcome,
    PspCaptureOutcome,
    UnknownPspScenarioTokenError,
)

_KNOWN_TOKENS = frozenset({"success", "decline", "timeout", "unknown_capture"})


class FakePspClient:
    def __init__(
        self,
        authorize_outcome: PspAuthorizeOutcome = PspAuthorizeOutcome.SUCCESS,
        capture_outcome: PspCaptureOutcome = PspCaptureOutcome.CAPTURED,
        lookup_outcome: PspCaptureLookupOutcome = PspCaptureLookupOutcome.CAPTURED,
    ) -> None:
        self.authorize_outcome = authorize_outcome
        self.capture_outcome = capture_outcome
        self.lookup_outcome = lookup_outcome
        self.authorize_calls: list[tuple[str, int]] = []
        # Только токены (issue #368) — ключ capture'а пишется отдельно, чтобы
        # существующие утверждения `capture_calls == ["success"]` не менялись.
        self.capture_calls: list[str] = []
        self.capture_idempotency_keys: list[str] = []
        self.lookup_capture_calls: list[tuple[str, str]] = []

    async def authorize(
        self, payment_method_token: str, amount: int
    ) -> PspAuthorizeOutcome:
        self.authorize_calls.append((payment_method_token, amount))
        if payment_method_token not in _KNOWN_TOKENS:
            raise UnknownPspScenarioTokenError(payment_method_token)
        return self.authorize_outcome

    async def capture(
        self, payment_method_token: str, idempotency_key: str
    ) -> PspCaptureOutcome:
        self.capture_calls.append(payment_method_token)
        self.capture_idempotency_keys.append(idempotency_key)
        if payment_method_token not in _KNOWN_TOKENS:
            raise UnknownPspScenarioTokenError(payment_method_token)
        return self.capture_outcome

    async def lookup_capture(
        self, payment_method_token: str, idempotency_key: str
    ) -> PspCaptureLookupOutcome:
        self.lookup_capture_calls.append((payment_method_token, idempotency_key))
        if payment_method_token not in _KNOWN_TOKENS:
            raise UnknownPspScenarioTokenError(payment_method_token)
        return self.lookup_outcome
