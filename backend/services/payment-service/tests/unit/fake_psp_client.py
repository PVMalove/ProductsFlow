"""Фейковый PspClient для юнит-тестов application handler'ов (issue #368) —
считает вызовы, чтобы тесты могли утверждать «PSP не переспрашивается» при
повторном idempotency-ключе."""

from domain.psp_client import (
    PspAuthorizeOutcome,
    PspCaptureOutcome,
    UnknownPspScenarioTokenError,
)

_KNOWN_TOKENS = frozenset({"success", "decline", "timeout", "unknown_capture"})


class FakePspClient:
    def __init__(
        self,
        authorize_outcome: PspAuthorizeOutcome = PspAuthorizeOutcome.SUCCESS,
        capture_outcome: PspCaptureOutcome = PspCaptureOutcome.CAPTURED,
    ) -> None:
        self.authorize_outcome = authorize_outcome
        self.capture_outcome = capture_outcome
        self.authorize_calls: list[tuple[str, int]] = []
        self.capture_calls: list[str] = []

    async def authorize(
        self, payment_method_token: str, amount: int
    ) -> PspAuthorizeOutcome:
        self.authorize_calls.append((payment_method_token, amount))
        if payment_method_token not in _KNOWN_TOKENS:
            raise UnknownPspScenarioTokenError(payment_method_token)
        return self.authorize_outcome

    async def capture(self, payment_method_token: str) -> PspCaptureOutcome:
        self.capture_calls.append(payment_method_token)
        if payment_method_token not in _KNOWN_TOKENS:
            raise UnknownPspScenarioTokenError(payment_method_token)
        return self.capture_outcome
