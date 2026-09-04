import uuid

import pytest

from domain.entities.ticket_message import TicketMessage
from domain.value_objects.ticket_id import TicketId


def _message(**overrides: object) -> TicketMessage:
    defaults: dict[str, object] = {
        "id": uuid.uuid4(),
        "ticket_id": TicketId.new_id(),
        "author_id": uuid.uuid4(),
        "body": "Hello",
    }
    defaults.update(overrides)
    return TicketMessage.create(**defaults)  # type: ignore[arg-type]


def test_ticket_message_direct_construction_raises_runtime_error() -> None:
    with pytest.raises(RuntimeError):
        TicketMessage(
            id=uuid.uuid4(),
            ticket_id=TicketId.new_id(),
            author_id=uuid.uuid4(),
            body="Hello",
        )


def test_ticket_message_edit_updates_body() -> None:
    message = _message()

    result = message.edit("Updated body")

    assert result.is_ok
    assert message.body == "Updated body"


def test_ticket_message_edit_rejects_system_messages() -> None:
    message = _message(is_system=True)

    result = message.edit("Updated body")

    assert result.is_err
    assert result.error.code == "message_immutable"
    assert message.body == "Hello"


def test_ticket_message_edit_rejects_already_deleted_messages() -> None:
    message = _message()
    assert message.delete().is_ok

    result = message.edit("Updated body")

    assert result.is_err
    assert result.error.code == "message_already_deleted"


def test_ticket_message_delete_soft_deletes_body() -> None:
    message = _message()

    result = message.delete()

    assert result.is_ok
    assert message.is_deleted is True
    assert message.body == "[Сообщение удалено]"


def test_ticket_message_delete_rejects_system_messages() -> None:
    message = _message(is_system=True)

    result = message.delete()

    assert result.is_err
    assert result.error.code == "message_immutable"
    assert message.is_deleted is False


def test_ticket_message_delete_rejects_already_deleted_messages() -> None:
    message = _message()
    assert message.delete().is_ok

    result = message.delete()

    assert result.is_err
    assert result.error.code == "message_already_deleted"
