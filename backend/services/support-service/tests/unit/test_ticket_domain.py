import uuid

import pytest
from kernel_domain.errors import ErrorType

from domain.entities.ticket import Ticket
from domain.events.ticket_domain_event import (
    TicketCreated,
    TicketMessageAdded,
    TicketMessageDeleted,
    TicketMessageEdited,
)
from domain.ticket_status import TicketStatus
from domain.value_objects.ticket_id import TicketId


def _create(**overrides: object) -> Ticket:
    defaults: dict[str, object] = {
        "author_id": uuid.uuid4(),
        "subject": "Subject",
        "first_message": "First message",
    }
    defaults.update(overrides)
    result = Ticket.create(**defaults)  # type: ignore[arg-type]
    assert result.is_ok
    return result.value


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

    result = Ticket.create(
        author_id=author_id,
        subject="  Не приходит заказ  ",
        first_message="  Помогите, пожалуйста.  ",
    )

    assert result.is_ok
    ticket = result.value
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
    result = Ticket.create(
        author_id=uuid.uuid4(), subject=subject, first_message="message"
    )

    assert result.is_err
    assert result.error.code == "invalid_subject"
    assert result.error.type is ErrorType.VALIDATION


@pytest.mark.parametrize("body", ["", " ", "x" * 10001])
def test_ticket_rejects_invalid_first_message(body: str) -> None:
    with pytest.raises(ValueError):
        Ticket.create(author_id=uuid.uuid4(), subject="subject", first_message=body)


def test_ticket_author_message_reopens_resolved_ticket() -> None:
    author_id = uuid.uuid4()
    ticket = _create(author_id=author_id)
    ticket.pull_events()

    assert ticket.change_status(TicketStatus.IN_PROGRESS, actor_category="admin").is_ok
    assert ticket.change_status(TicketStatus.RESOLVED, actor_category="admin").is_ok
    result = ticket.add_message(
        author_id=author_id, body="It is still broken", actor_category="user"
    )

    assert result.is_ok
    message = result.value
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
    ticket = _create(author_id=author_id, first_message="Original message")
    ticket.pull_events()

    result = ticket.edit_message(
        message_id=ticket.messages[0].id,
        author_id=author_id,
        body="Corrected message",
        actor_category="user",
    )

    assert result.is_ok
    assert ticket.messages[0].body == "Corrected message"
    event = ticket.pull_events()[0]
    assert isinstance(event, TicketMessageEdited)
    assert event.message_id == ticket.messages[0].id
    assert not hasattr(event, "body")


def test_ticket_can_soft_delete_a_message_and_preserve_its_thread_position() -> None:
    author_id = uuid.uuid4()
    ticket = _create(author_id=author_id, first_message="Original message")
    ticket.pull_events()
    second_result = ticket.add_message(
        author_id=author_id, body="Second message", actor_category="user"
    )
    assert second_result.is_ok
    second = second_result.value
    ticket.pull_events()
    original_created_at = ticket.messages[0].created_at
    original_id = ticket.messages[0].id

    result = ticket.delete_message(
        message_id=original_id,
        actor_id=uuid.uuid4(),
        actor_category="admin",
    )

    assert result.is_ok
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


def test_ticket_rejects_skipped_status_transition() -> None:
    ticket = _create()

    result = ticket.change_status(TicketStatus.RESOLVED, actor_category="admin")

    assert result.is_err
    assert result.error.code == "invalid_status_transition"
    assert result.error.type is ErrorType.CONFLICT


def test_ticket_rejects_mutations_on_a_closed_ticket() -> None:
    ticket = _create()
    assert ticket.change_status(TicketStatus.IN_PROGRESS, actor_category="admin").is_ok
    assert ticket.change_status(TicketStatus.RESOLVED, actor_category="admin").is_ok
    assert ticket.change_status(TicketStatus.CLOSED, actor_category="admin").is_ok

    add_result = ticket.add_message(
        author_id=uuid.uuid4(), body="No longer possible", actor_category="admin"
    )
    assert add_result.is_err
    assert add_result.error.code == "ticket_closed"
    assert add_result.error.type is ErrorType.CONFLICT

    status_result = ticket.change_status(
        TicketStatus.IN_PROGRESS, actor_category="admin"
    )
    assert status_result.is_err
    assert status_result.error.code == "ticket_closed"


def test_ticket_rejects_editing_unknown_or_foreign_messages() -> None:
    author_id = uuid.uuid4()
    ticket = _create(author_id=author_id)

    unknown_result = ticket.edit_message(
        message_id=uuid.uuid4(),
        author_id=author_id,
        body="Changed",
        actor_category="user",
    )
    assert unknown_result.is_err
    assert unknown_result.error.code == "message_not_found"

    foreign_result = ticket.edit_message(
        message_id=ticket.messages[0].id,
        author_id=uuid.uuid4(),
        body="Changed",
        actor_category="user",
    )
    assert foreign_result.is_err
    assert foreign_result.error.code == "message_not_found"


def test_ticket_rejects_editing_system_and_deleted_messages() -> None:
    author_id = uuid.uuid4()
    ticket = _create(author_id=author_id)
    system_result = ticket.add_message(
        author_id=uuid.uuid4(),
        body="System message",
        actor_category="admin",
        is_system=True,
    )
    assert system_result.is_ok
    system_message = system_result.value
    assert system_message.author_id is not None

    immutable_result = ticket.edit_message(
        message_id=system_message.id,
        author_id=system_message.author_id,
        body="Changed",
        actor_category="admin",
    )
    assert immutable_result.is_err
    assert immutable_result.error.code == "message_immutable"

    delete_result = ticket.delete_message(
        message_id=ticket.messages[0].id,
        actor_id=author_id,
        actor_category="user",
    )
    assert delete_result.is_ok

    already_deleted_result = ticket.edit_message(
        message_id=ticket.messages[0].id,
        author_id=author_id,
        body="Changed",
        actor_category="user",
    )
    assert already_deleted_result.is_err
    assert already_deleted_result.error.code == "message_already_deleted"


def test_admin_can_soft_delete_a_message_after_ticket_closure() -> None:
    ticket = _create()
    assert ticket.change_status(TicketStatus.IN_PROGRESS, actor_category="admin").is_ok
    assert ticket.change_status(TicketStatus.RESOLVED, actor_category="admin").is_ok
    assert ticket.change_status(TicketStatus.CLOSED, actor_category="admin").is_ok

    result = ticket.delete_message(
        message_id=ticket.messages[0].id,
        actor_id=uuid.uuid4(),
        actor_category="admin",
    )

    assert result.is_ok
    assert ticket.messages[0].is_deleted is True


def test_non_admin_cannot_delete_a_message_on_a_closed_ticket() -> None:
    author_id = uuid.uuid4()
    ticket = _create(author_id=author_id)
    assert ticket.change_status(TicketStatus.IN_PROGRESS, actor_category="admin").is_ok
    assert ticket.change_status(TicketStatus.RESOLVED, actor_category="admin").is_ok
    assert ticket.change_status(TicketStatus.CLOSED, actor_category="admin").is_ok

    result = ticket.delete_message(
        message_id=ticket.messages[0].id,
        actor_id=author_id,
        actor_category="user",
    )

    assert result.is_err
    assert result.error.code == "ticket_closed"


def test_delete_message_rejects_unknown_or_foreign_messages() -> None:
    author_id = uuid.uuid4()
    ticket = _create(author_id=author_id)

    unknown_result = ticket.delete_message(
        message_id=uuid.uuid4(), actor_id=author_id, actor_category="user"
    )
    assert unknown_result.is_err
    assert unknown_result.error.code == "message_not_found"

    foreign_result = ticket.delete_message(
        message_id=ticket.messages[0].id, actor_id=uuid.uuid4(), actor_category="user"
    )
    assert foreign_result.is_err
    assert foreign_result.error.code == "message_not_found"


def test_delete_message_rejects_system_and_already_deleted_messages() -> None:
    author_id = uuid.uuid4()
    ticket = _create(author_id=author_id)
    system_result = ticket.add_message(
        author_id=uuid.uuid4(),
        body="System message",
        actor_category="admin",
        is_system=True,
    )
    assert system_result.is_ok
    system_message = system_result.value
    assert system_message.author_id is not None

    immutable_result = ticket.delete_message(
        message_id=system_message.id,
        actor_id=system_message.author_id,
        actor_category="admin",
    )
    assert immutable_result.is_err
    assert immutable_result.error.code == "message_immutable"

    first_delete = ticket.delete_message(
        message_id=ticket.messages[0].id,
        actor_id=author_id,
        actor_category="user",
    )
    assert first_delete.is_ok

    second_delete = ticket.delete_message(
        message_id=ticket.messages[0].id,
        actor_id=author_id,
        actor_category="user",
    )
    assert second_delete.is_err
    assert second_delete.error.code == "message_already_deleted"


def test_user_deletion_anonymizes_ticket_and_closes_it_once() -> None:
    author_id = uuid.uuid4()
    ticket = _create(author_id=author_id)
    ticket.pull_events()

    result = ticket.anonymize_deleted_user(author_id)

    assert result.is_ok
    assert result.value is True
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

    second_result = ticket.anonymize_deleted_user(author_id)
    assert second_result.is_ok
    assert second_result.value is False
    assert len(ticket.messages) == 2
