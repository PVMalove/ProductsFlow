import uuid

import pytest

from domain.events.ticket_created import TicketCreated
from domain.ticket import (
    InvalidStatusTransitionError,
    Ticket,
    TicketClosedError,
    TicketStatus,
)


def test_ticket_creation_builds_open_ticket_and_first_message() -> None:
    author_id = uuid.uuid4()

    ticket = Ticket.create(
        author_id=author_id,
        subject="  Не приходит заказ  ",
        first_message="  Помогите, пожалуйста.  ",
    )

    assert ticket.author_id == author_id
    assert ticket.status is TicketStatus.OPEN
    assert ticket.subject == "Не приходит заказ"
    assert len(ticket.messages) == 1
    assert ticket.messages[0].author_id == author_id
    assert ticket.messages[0].body == "Помогите, пожалуйста."
    event = ticket.pull_events()[0]
    assert isinstance(event, TicketCreated)
    assert event.event_type == "ticket.created.v1"


@pytest.mark.parametrize("subject", ["", " ", "x" * 201])
def test_ticket_rejects_invalid_subject(subject: str) -> None:
    with pytest.raises(ValueError):
        Ticket.create(author_id=uuid.uuid4(), subject=subject, first_message="message")


@pytest.mark.parametrize("body", ["", " ", "x" * 10001])
def test_ticket_rejects_invalid_first_message(body: str) -> None:
    with pytest.raises(ValueError):
        Ticket.create(author_id=uuid.uuid4(), subject="subject", first_message=body)


def test_ticket_author_message_reopens_resolved_ticket() -> None:
    author_id = uuid.uuid4()
    ticket = Ticket.create(
        author_id=author_id, subject="Subject", first_message="First message"
    )
    ticket.pull_events()

    ticket.change_status(TicketStatus.IN_PROGRESS, actor_category="admin")
    ticket.change_status(TicketStatus.RESOLVED, actor_category="admin")
    message = ticket.add_message(
        author_id=author_id, body="It is still broken", actor_category="user"
    )

    assert message.author_id == author_id
    assert ticket.status is TicketStatus.IN_PROGRESS
    events = ticket.pull_events()
    assert [getattr(event, "event_type", None) for event in events] == [
        "ticket.status_changed.v1",
        "ticket.status_changed.v1",
        "ticket.message_added.v1",
        "ticket.status_changed.v1",
    ]
    assert all(not hasattr(event, "body") for event in events)


def test_ticket_rejects_skipped_status_and_closed_mutations() -> None:
    ticket = Ticket.create(
        author_id=uuid.uuid4(), subject="Subject", first_message="First message"
    )

    with pytest.raises(InvalidStatusTransitionError):
        ticket.change_status(TicketStatus.RESOLVED, actor_category="admin")

    ticket.change_status(TicketStatus.IN_PROGRESS, actor_category="admin")
    ticket.change_status(TicketStatus.RESOLVED, actor_category="admin")
    ticket.change_status(TicketStatus.CLOSED, actor_category="admin")

    with pytest.raises(TicketClosedError):
        ticket.add_message(
            author_id=uuid.uuid4(), body="No longer possible", actor_category="admin"
        )
    with pytest.raises(TicketClosedError):
        ticket.change_status(TicketStatus.IN_PROGRESS, actor_category="admin")
