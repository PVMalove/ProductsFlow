"""Domain-агрегат PaymentAuthorization (ADR 0016, issue #368) — Always-Valid
Domain state machine, зеркалит test_inventory_entity.py."""

from domain.entities.payment_authorization import (
    PaymentAuthorization,
    PaymentAuthorizationStatus,
)
from domain.psp_client import (
    PspAuthorizeOutcome,
    PspCaptureLookupOutcome,
    PspCaptureOutcome,
)


def test_create_rejects_non_positive_amount() -> None:
    result = PaymentAuthorization.create(
        "key-1", 0, "success", PspAuthorizeOutcome.SUCCESS
    )

    assert result.is_err
    assert result.error.code == "invalid_amount"


def test_create_success_outcome_authorizes() -> None:
    result = PaymentAuthorization.create(
        "key-1", 1000, "success", PspAuthorizeOutcome.SUCCESS
    )

    assert result.is_ok
    payment = result.value
    assert payment.status is PaymentAuthorizationStatus.AUTHORIZED
    assert payment.idempotency_key == "key-1"
    assert payment.amount == 1000
    assert payment.payment_method_token == "success"
    assert payment.void_idempotency_key is None
    assert payment.capture_idempotency_key is None


def test_create_decline_outcome_is_declined() -> None:
    result = PaymentAuthorization.create(
        "key-1", 1000, "decline", PspAuthorizeOutcome.DECLINE
    )

    assert result.is_ok
    assert result.value.status is PaymentAuthorizationStatus.DECLINED


def test_create_timeout_outcome_is_authorization_unknown() -> None:
    result = PaymentAuthorization.create(
        "key-1", 1000, "timeout", PspAuthorizeOutcome.TIMEOUT
    )

    assert result.is_ok
    assert result.value.status is PaymentAuthorizationStatus.AUTHORIZATION_UNKNOWN


def _authorized() -> PaymentAuthorization:
    return PaymentAuthorization.create(
        "key-1", 1000, "success", PspAuthorizeOutcome.SUCCESS
    ).value


def test_void_from_authorized_succeeds_once() -> None:
    payment = _authorized()

    result = payment.void("void-key-1")

    assert result.is_ok
    assert payment.status is PaymentAuthorizationStatus.VOIDED
    assert payment.void_idempotency_key == "void-key-1"


def test_void_repeated_with_same_key_is_a_noop_ok() -> None:
    payment = _authorized()
    first = payment.void("void-key-1")
    assert first.is_ok

    second = payment.void("void-key-1")

    assert second.is_ok
    assert payment.status is PaymentAuthorizationStatus.VOIDED


def test_void_repeated_with_different_key_conflicts() -> None:
    payment = _authorized()
    payment.void("void-key-1")

    result = payment.void("void-key-2")

    assert result.is_err
    assert result.error.code == "invalid_authorization_state"


def test_void_from_declined_conflicts() -> None:
    payment = PaymentAuthorization.create(
        "key-1", 1000, "decline", PspAuthorizeOutcome.DECLINE
    ).value

    result = payment.void("void-key-1")

    assert result.is_err
    assert result.error.code == "invalid_authorization_state"


def test_capture_success_outcome_from_authorized_captures() -> None:
    payment = _authorized()

    result = payment.capture("capture-key-1", PspCaptureOutcome.CAPTURED)

    assert result.is_ok
    assert payment.status is PaymentAuthorizationStatus.CAPTURED
    assert payment.capture_idempotency_key == "capture-key-1"


def test_capture_unknown_outcome_from_authorized_is_capture_unknown() -> None:
    payment = _authorized()

    result = payment.capture("capture-key-1", PspCaptureOutcome.UNKNOWN)

    assert result.is_ok
    assert payment.status is PaymentAuthorizationStatus.CAPTURE_UNKNOWN


def test_capture_repeated_with_same_key_is_a_noop_ok() -> None:
    payment = _authorized()
    first = payment.capture("capture-key-1", PspCaptureOutcome.CAPTURED)
    assert first.is_ok

    second = payment.capture("capture-key-1", PspCaptureOutcome.CAPTURED)

    assert second.is_ok
    assert payment.status is PaymentAuthorizationStatus.CAPTURED


def test_capture_unknown_then_different_key_is_reconciliation_conflict() -> None:
    payment = _authorized()
    payment.capture("capture-key-1", PspCaptureOutcome.UNKNOWN)

    result = payment.capture("capture-key-2", PspCaptureOutcome.CAPTURED)

    assert result.is_err
    assert result.error.code == "capture_pending_reconciliation"
    assert payment.status is PaymentAuthorizationStatus.CAPTURE_UNKNOWN


def test_capture_from_non_authorized_state_conflicts() -> None:
    payment = PaymentAuthorization.create(
        "key-1", 1000, "decline", PspAuthorizeOutcome.DECLINE
    ).value

    result = payment.capture("capture-key-1", PspCaptureOutcome.CAPTURED)

    assert result.is_err
    assert result.error.code == "invalid_authorization_state"


def test_reconcile_capture_found_at_the_psp_captures() -> None:
    payment = _authorized()
    payment.capture("capture-key-1", PspCaptureOutcome.UNKNOWN)

    result = payment.reconcile_capture(
        "capture-key-1", PspCaptureLookupOutcome.CAPTURED
    )

    assert result.is_ok
    assert payment.status is PaymentAuthorizationStatus.CAPTURED
    assert payment.capture_idempotency_key == "capture-key-1"


def test_reconcile_capture_not_found_returns_to_authorized_and_allows_a_new_key() -> (
    None
):
    """Issue #374, DoD 3: a repeat capture is allowed only after the absence of
    the operation is confirmed — the existing `capture()` then accepts a new key
    from AUTHORIZED unchanged."""
    payment = _authorized()
    payment.capture("capture-key-1", PspCaptureOutcome.UNKNOWN)

    reconciled = payment.reconcile_capture(
        "capture-key-1", PspCaptureLookupOutcome.NOT_FOUND
    )

    assert reconciled.is_ok
    assert payment.status is PaymentAuthorizationStatus.AUTHORIZED
    assert payment.capture_idempotency_key == "capture-key-1"

    recaptured = payment.capture("capture-key-2", PspCaptureOutcome.CAPTURED)

    assert recaptured.is_ok
    assert payment.status is PaymentAuthorizationStatus.CAPTURED
    assert payment.capture_idempotency_key == "capture-key-2"


def test_reconcile_capture_with_another_key_is_not_found() -> None:
    payment = _authorized()
    payment.capture("capture-key-1", PspCaptureOutcome.UNKNOWN)

    result = payment.reconcile_capture(
        "capture-key-2", PspCaptureLookupOutcome.CAPTURED
    )

    assert result.is_err
    assert result.error.code == "authorization_not_found"
    assert payment.status is PaymentAuthorizationStatus.CAPTURE_UNKNOWN


def test_reconcile_capture_of_an_already_final_capture_is_a_noop_ok() -> None:
    payment = _authorized()
    payment.capture("capture-key-1", PspCaptureOutcome.CAPTURED)

    result = payment.reconcile_capture(
        "capture-key-1", PspCaptureLookupOutcome.NOT_FOUND
    )

    assert result.is_ok
    assert payment.status is PaymentAuthorizationStatus.CAPTURED
