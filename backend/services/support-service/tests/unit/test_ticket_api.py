from pydantic import ValidationError

from api.schemas import (
    TicketCreateRequest,
    TicketMessageCreateRequest,
    TicketStatusChangeRequest,
)
from domain.ticket_status import TicketStatus


def test_ticket_create_request_trims_plaintext() -> None:
    request = TicketCreateRequest(subject="  Subject  ", first_message="  Body  ")

    assert request.subject == "Subject"
    assert request.first_message == "Body"


def test_ticket_create_request_rejects_non_text_values() -> None:
    try:
        TicketCreateRequest(subject=123, first_message="Body")  # type: ignore[arg-type]
    except ValidationError:
        return
    raise AssertionError("non-text subject must be rejected")


def test_ticket_mutation_requests_validate_and_trim_plaintext() -> None:
    message = TicketMessageCreateRequest(body="  Reply  ")
    status_request = TicketStatusChangeRequest(status=TicketStatus.IN_PROGRESS)

    assert message.body == "Reply"
    assert status_request.status is TicketStatus.IN_PROGRESS
