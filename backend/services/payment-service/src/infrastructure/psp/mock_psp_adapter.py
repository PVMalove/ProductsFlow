"""Детерминированный Test PSP-адаптер (ADR 0016, issue #368, брифа D4).

Это мок — детерминированная заглушка с заранее заданными исходами, не
test-утилита (ревью явно потребовало это имя, не переименовывать обратно на
`TestPspAdapter`). `payment_method_token` сам и есть селектор сценария: чистая
табличная функция без I/O и без рандома, допустимая только при
`APP_ENV != "prod"` (гейт — `core/psp.py::build_psp_client`, не этот класс)."""

from domain.psp_client import (
    PspAuthorizeOutcome,
    PspCaptureOutcome,
    PspClient,
    UnknownPspScenarioTokenError,
)

_AUTHORIZE_OUTCOMES: dict[str, PspAuthorizeOutcome] = {
    "success": PspAuthorizeOutcome.SUCCESS,
    "decline": PspAuthorizeOutcome.DECLINE,
    "timeout": PspAuthorizeOutcome.TIMEOUT,
    # Селектор для будущего capture-исхода — сама авторизация должна дойти до
    # AUTHORIZED, иначе `capture` для неё никогда не станет достижимым.
    "unknown_capture": PspAuthorizeOutcome.SUCCESS,
}

_CAPTURE_OUTCOMES: dict[str, PspCaptureOutcome] = {
    "success": PspCaptureOutcome.CAPTURED,
    "unknown_capture": PspCaptureOutcome.UNKNOWN,
}


class MockPspAdapter:
    """Реализация `domain.psp_client.PspClient`. Ни один метод не выполняет
    сетевых вызовов — исход определяется исключительно переданным токеном."""

    async def authorize(
        self, payment_method_token: str, amount: int
    ) -> PspAuthorizeOutcome:
        try:
            return _AUTHORIZE_OUTCOMES[payment_method_token]
        except KeyError as exc:
            raise UnknownPspScenarioTokenError(payment_method_token) from exc

    async def capture(self, payment_method_token: str) -> PspCaptureOutcome:
        try:
            return _CAPTURE_OUTCOMES[payment_method_token]
        except KeyError as exc:
            raise UnknownPspScenarioTokenError(payment_method_token) from exc


# Статическая структурная проверка (мирор inventory's repository-implementation
# assertion): mypy убеждается, что MockPspAdapter реализует весь PspClient-порт.
_mock_psp_adapter_implementation: type[PspClient] = MockPspAdapter
