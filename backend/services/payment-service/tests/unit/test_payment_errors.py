"""Стабильность публичного контракта ошибок payment (ADR 0014, issue #368)."""

from kernel_domain.errors import ErrorType

from domain.errors import PaymentErrors


def test_invalid_amount_is_a_stable_validation_error() -> None:
    error = PaymentErrors.invalid_amount()

    assert error.code == "invalid_amount"
    assert error.type is ErrorType.VALIDATION
    assert error.description
    assert error.invalid_field == "amount"


def test_unknown_test_scenario_token_is_a_stable_validation_error() -> None:
    error = PaymentErrors.unknown_test_scenario_token()

    assert error.code == "unknown_test_scenario_token"
    assert error.type is ErrorType.VALIDATION
    assert error.description
    assert error.invalid_field == "payment_method_token"


def test_authorization_not_found_is_a_stable_not_found_error() -> None:
    error = PaymentErrors.authorization_not_found()

    assert error.code == "authorization_not_found"
    assert error.type is ErrorType.NOT_FOUND
    assert error.description


def test_idempotency_conflict_is_a_stable_conflict_error() -> None:
    error = PaymentErrors.idempotency_conflict()

    assert error.code == "idempotency_conflict"
    assert error.type is ErrorType.CONFLICT
    assert error.description


def test_invalid_authorization_state_is_a_stable_conflict_error() -> None:
    error = PaymentErrors.invalid_authorization_state()

    assert error.code == "invalid_authorization_state"
    assert error.type is ErrorType.CONFLICT
    assert error.description


def test_capture_pending_reconciliation_is_a_stable_conflict_error() -> None:
    error = PaymentErrors.capture_pending_reconciliation()

    assert error.code == "capture_pending_reconciliation"
    assert error.type is ErrorType.CONFLICT
    assert error.description
