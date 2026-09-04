import uuid

import pytest

from domain.entities.ticket import (
    InvalidStatusTransitionError,
    Ticket,
    TicketClosedError,
)
from domain.events.ticket_domain_event import (
    TicketCreated,
    TicketMessageAdded,
    TicketMessageDeleted,
    TicketMessageEdited,
)
from domain.ticket_status import TicketStatus
from domain.value_objects.ticket_id import TicketId


def test_ticket_id_new_id_returns_a_uuid() -> None:
    ticket_id = TicketId.new_id()

    assert isinstance(ticket_id.value, uuid.UUID)


def test_ticket_id_direct_construction_raises_runtime_error() -> None:
    with pytest.raises(RuntimeError):
        TicketId(uuid.uuid4())


def test_ticket_direct_construction_raises_runtime_error() -> None:
    with pytest.raises(RuntimeError):
        Ticket(TicketId.new_id(), author_id=uuid.uuid4(), subject="Subject")


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


def test_ticket_author_can_edit_their_message_without_exposing_text_in_event() -> None:
    author_id = uuid.uuid4()
    ticket = Ticket.create(
        author_id=author_id, subject="Subject", first_message="Original message"
    )
    ticket.pull_events()

    ticket.edit_message(
        message_id=ticket.messages[0].id,
        author_id=author_id,
        body="Corrected message",
        actor_category="user",
    )

    assert ticket.messages[0].body == "Corrected message"
    event = ticket.pull_events()[0]
    assert isinstance(event, TicketMessageEdited)
    assert event.message_id == ticket.messages[0].id
    assert not hasattr(event, "body")


def test_ticket_can_soft_delete_a_message_and_preserve_its_thread_position() -> None:
    author_id = uuid.uuid4()
    ticket = Ticket.create(
        author_id=author_id, subject="Subject", first_message="Original message"
    )
    ticket.pull_events()
    second = ticket.add_message(
        author_id=author_id, body="Second message", actor_category="user"
    )
    ticket.pull_events()
    original_created_at = ticket.messages[0].created_at
    original_id = ticket.messages[0].id

    ticket.delete_message(
        message_id=original_id,
        actor_id=uuid.uuid4(),
        actor_category="admin",
    )

    deleted = ticket.messages[0]
    assert deleted.id == original_id
    assert deleted.author_id == author_id
    assert deleted.created_at == original_created_at
    assert deleted.body == "[Сообщение удалено]"
    assert deleted.is_deleted is True
    assert ticket.messages[1] is second
    event = ticket.pull_events()[0]
    assert isinstance(event, TicketMessageDeleted)
    assert event.message_id == original_id
    assert not hasattr(event, "body")


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


def test_ticket_rejects_editing_system_and_deleted_messages() -> None:
    author_id = uuid.uuid4()
    ticket = Ticket.create(
        author_id=author_id, subject="Subject", first_message="First message"
    )
    system_message = ticket.add_message(
        author_id=uuid.uuid4(),
        body="System message",
        actor_category="admin",
        is_system=True,
    )
    assert system_message.author_id is not None
    with pytest.raises(ValueError):
        ticket.edit_message(
            message_id=system_message.id,
            author_id=system_message.author_id,
            body="Changed",
            actor_category="admin",
        )

    ticket.delete_message(
        message_id=ticket.messages[0].id,
        actor_id=author_id,
        actor_category="user",
    )
    with pytest.raises(ValueError):
        ticket.edit_message(
            message_id=ticket.messages[0].id,
            author_id=author_id,
            body="Changed",
            actor_category="user",
        )


def test_admin_can_soft_delete_a_message_after_ticket_closure() -> None:
    ticket = Ticket.create(
        author_id=uuid.uuid4(), subject="Subject", first_message="First message"
    )
    ticket.change_status(TicketStatus.IN_PROGRESS, actor_category="admin")
    ticket.change_status(TicketStatus.RESOLVED, actor_category="admin")
    ticket.change_status(TicketStatus.CLOSED, actor_category="admin")

    ticket.delete_message(
        message_id=ticket.messages[0].id,
        actor_id=uuid.uuid4(),
        actor_category="admin",
    )

    assert ticket.messages[0].is_deleted is True


def test_user_deletion_anonymizes_ticket_and_closes_it_once() -> None:
    author_id = uuid.uuid4()
    ticket = Ticket.create(
        author_id=author_id, subject="Subject", first_message="First message"
    )
    ticket.pull_events()

    affected = ticket.anonymize_deleted_user(author_id)

    assert affected is True
    assert ticket.author_id is None
    assert ticket.status is TicketStatus.CLOSED
    assert ticket.messages[0].author_id is None
    assert len(ticket.messages) == 2
    system_message = ticket.messages[-1]
    assert system_message.author_id is None
    assert system_message.is_system is True
    assert system_message.body == "[Пользователь удалён]"
    events = ticket.pull_events()
    assert [getattr(event, "event_type", None) for event in events] == [
        "ticket.status_changed.v1",
        "ticket.message_added.v1",
    ]
    assert isinstance(events[1], TicketMessageAdded)
    assert not hasattr(events[1], "body")

    assert ticket.anonymize_deleted_user(author_id) is False
    assert len(ticket.messages) == 2
