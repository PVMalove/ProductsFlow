from kernel_domain.errors import ErrorType

from domain.errors import IdentityErrors


def test_invalid_email_carries_stable_code_and_public_field() -> None:
    error = IdentityErrors.invalid_email()

    assert error.code == "invalid_email"
    assert error.type is ErrorType.VALIDATION
    assert error.invalid_field == "email"
    assert error.description == "Некорректный формат email"


def test_password_too_short_carries_stable_code_and_public_field() -> None:
    error = IdentityErrors.password_too_short()

    assert error.code == "password_too_short"
    assert error.type is ErrorType.VALIDATION
    assert error.invalid_field == "password"


def test_password_missing_lowercase_carries_stable_code_and_public_field() -> None:
    error = IdentityErrors.password_missing_lowercase()

    assert error.code == "password_missing_lowercase"
    assert error.type is ErrorType.VALIDATION
    assert error.invalid_field == "password"


def test_password_missing_digit_carries_stable_code_and_public_field() -> None:
    error = IdentityErrors.password_missing_digit()

    assert error.code == "password_missing_digit"
    assert error.type is ErrorType.VALIDATION
    assert error.invalid_field == "password"


def test_email_already_registered_carries_stable_code_without_a_field() -> None:
    error = IdentityErrors.email_already_registered()

    assert error.code == "email_already_registered"
    assert error.type is ErrorType.CONFLICT
    assert error.invalid_field is None
    assert error.description == "Email уже зарегистрирован"


def test_invalid_credentials_carries_stable_code_without_a_field() -> None:
    error = IdentityErrors.invalid_credentials()

    assert error.code == "invalid_credentials"
    assert error.type is ErrorType.UNAUTHORIZED
    assert error.invalid_field is None


def test_old_password_mismatch_shares_the_invalid_credentials_code() -> None:
    error = IdentityErrors.old_password_mismatch()

    assert error.code == "invalid_credentials"
    assert error.type is ErrorType.UNAUTHORIZED


def test_user_deactivated_carries_stable_code_without_a_field() -> None:
    error = IdentityErrors.user_deactivated()

    assert error.code == "user_deactivated"
    assert error.type is ErrorType.FORBIDDEN
    assert error.invalid_field is None


def test_already_deactivated_carries_stable_code_without_a_field() -> None:
    error = IdentityErrors.already_deactivated()

    assert error.code == "already_deactivated"
    assert error.type is ErrorType.CONFLICT
    assert error.invalid_field is None


def test_user_deleted_carries_stable_code_without_a_field() -> None:
    error = IdentityErrors.user_deleted()

    assert error.code == "user_deleted"
    assert error.type is ErrorType.FORBIDDEN
    assert error.invalid_field is None


def test_already_active_carries_stable_code_without_a_field() -> None:
    error = IdentityErrors.already_active()

    assert error.code == "already_active"
    assert error.type is ErrorType.CONFLICT
    assert error.invalid_field is None


def test_already_deleted_carries_stable_code_without_a_field() -> None:
    error = IdentityErrors.already_deleted()

    assert error.code == "already_deleted"
    assert error.type is ErrorType.CONFLICT
    assert error.invalid_field is None


def test_role_unchanged_carries_stable_code_without_reflecting_the_role() -> None:
    error = IdentityErrors.role_unchanged()

    assert error.code == "role_unchanged"
    assert error.type is ErrorType.CONFLICT
    assert error.invalid_field is None


def test_cannot_deactivate_self_carries_stable_code_without_a_field() -> None:
    error = IdentityErrors.cannot_deactivate_self()

    assert error.code == "cannot_deactivate_self"
    assert error.type is ErrorType.FORBIDDEN
    assert error.invalid_field is None


def test_user_not_found_carries_stable_code_without_a_field() -> None:
    error = IdentityErrors.user_not_found()

    assert error.code == "user_not_found"
    assert error.type is ErrorType.NOT_FOUND
    assert error.invalid_field is None
