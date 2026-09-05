from kernel_domain.errors import ErrorType

from domain.errors import SupportErrors


def test_invalid_subject_carries_stable_code_and_public_field() -> None:
    error = SupportErrors.invalid_subject()

    assert error.code == "invalid_subject"
    assert error.type is ErrorType.VALIDATION
    assert error.invalid_field == "subject"


def test_invalid_first_message_carries_stable_code_and_public_field() -> None:
    error = SupportErrors.invalid_first_message()

    assert error.code == "invalid_first_message"
    assert error.type is ErrorType.VALIDATION
    assert error.invalid_field == "first_message"


def test_invalid_body_carries_stable_code_and_public_field() -> None:
    error = SupportErrors.invalid_body()

    assert error.code == "invalid_body"
    assert error.type is ErrorType.VALIDATION
    assert error.invalid_field == "body"


def test_ticket_closed_carries_stable_code_without_a_field() -> None:
    error = SupportErrors.ticket_closed()

    assert error.code == "ticket_closed"
    assert error.type is ErrorType.CONFLICT
    assert error.invalid_field is None


def test_invalid_status_transition_carries_stable_code_without_a_field() -> None:
    error = SupportErrors.invalid_status_transition()

    assert error.code == "invalid_status_transition"
    assert error.type is ErrorType.CONFLICT
    assert error.invalid_field is None


def test_message_not_found_carries_stable_code_without_a_field() -> None:
    error = SupportErrors.message_not_found()

    assert error.code == "message_not_found"
    assert error.type is ErrorType.NOT_FOUND
    assert error.invalid_field is None


def test_message_immutable_carries_stable_code_without_a_field() -> None:
    error = SupportErrors.message_immutable()

    assert error.code == "message_immutable"
    assert error.type is ErrorType.CONFLICT
    assert error.invalid_field is None


def test_message_already_deleted_carries_stable_code_without_a_field() -> None:
    error = SupportErrors.message_already_deleted()

    assert error.code == "message_already_deleted"
    assert error.type is ErrorType.CONFLICT
    assert error.invalid_field is None


def test_ticket_not_found_carries_the_existing_bff_visible_code() -> None:
    error = SupportErrors.ticket_not_found()

    assert error.code == "TICKET_NOT_FOUND"
    assert error.type is ErrorType.NOT_FOUND


def test_ticket_message_not_found_carries_the_existing_bff_visible_code() -> None:
    error = SupportErrors.ticket_message_not_found()

    assert error.code == "TICKET_MESSAGE_NOT_FOUND"
    assert error.type is ErrorType.NOT_FOUND


def test_ticket_message_immutable_reflects_the_rejected_action() -> None:
    error = SupportErrors.ticket_message_immutable("удалить")

    assert error.code == "TICKET_MESSAGE_IMMUTABLE"
    assert error.type is ErrorType.CONFLICT
    assert "удалить" in error.description


def test_ticket_closed_conflict_carries_the_existing_bff_visible_code() -> None:
    error = SupportErrors.ticket_closed_conflict()

    assert error.code == "TICKET_CLOSED"
    assert error.type is ErrorType.CONFLICT


def test_ticket_status_transition_rejected_carries_the_existing_bff_visible_code() -> (
    None
):
    error = SupportErrors.ticket_status_transition_rejected()

    assert error.code == "INVALID_STATUS_TRANSITION"
    assert error.type is ErrorType.CONFLICT


def test_forbidden_carries_the_existing_bff_visible_code() -> None:
    error = SupportErrors.forbidden()

    assert error.code == "FORBIDDEN"
    assert error.type is ErrorType.FORBIDDEN
