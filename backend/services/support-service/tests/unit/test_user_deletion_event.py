import json
import uuid
from types import SimpleNamespace

import pytest

from api.worker import (
    _message_id,
    _parse_deleted_user_event,
    _parse_user_event_snapshot,
)
from application.commands import (
    ProcessUserDeletionCommand,
    ProcessUserDeletionCommandHandler,
)


def _message(
    *, body: bytes, message_id: object = "42", event_type: str = "user.deleted.v1"
) -> SimpleNamespace:
    return SimpleNamespace(
        body=body,
        message_id=message_id,
        type=event_type,
        routing_key=event_type,
    )


def test_worker_parses_user_deleted_event() -> None:
    user_id = uuid.uuid4()

    event = _parse_deleted_user_event(
        _message(  # type: ignore[arg-type]
            body=json.dumps({"user_id": str(user_id)}).encode()
        )
    )

    assert event.user_id == user_id


@pytest.mark.parametrize(
    "message",
    [
        _message(body=b"not json"),
        _message(body=b"{}"),
        _message(body=b"{}", event_type="user.registered.v1"),
        _message(body=b"{}", message_id="not-a-number"),
    ],
)
def test_worker_rejects_malformed_deletion_delivery(message: SimpleNamespace) -> None:
    with pytest.raises(ValueError):
        if message.message_id == "not-a-number":
            _message_id(message)  # type: ignore[arg-type]
        else:
            _parse_deleted_user_event(message)  # type: ignore[arg-type]


@pytest.mark.asyncio
async def test_user_deletion_handler_delegates_to_transactional_port() -> None:
    class FakeDeletionPort:
        def __init__(self) -> None:
            self.call: tuple[int, uuid.UUID] | None = None

        async def process_user_deleted(
            self, *, message_id: int, user_id: uuid.UUID
        ) -> bool:
            self.call = (message_id, user_id)
            return True

    user_id = uuid.uuid4()
    port = FakeDeletionPort()

    result = await ProcessUserDeletionCommandHandler(port).execute(
        ProcessUserDeletionCommand(message_id=7, user_id=user_id)
    )

    assert result is True
    assert port.call == (7, user_id)


def test_parse_user_event_snapshot_defaults_registered_role_and_active() -> None:
    user_id = uuid.uuid4()

    snapshot = _parse_user_event_snapshot(
        "user.registered.v1", json.dumps({"user_id": str(user_id)}).encode()
    )

    assert snapshot.user_id == user_id
    assert snapshot.role == "user"
    assert snapshot.is_active is True
    assert snapshot.deleted is False


def test_parse_user_event_snapshot_tombstones_a_deleted_user() -> None:
    user_id = uuid.uuid4()

    snapshot = _parse_user_event_snapshot(
        "user.deleted.v1", json.dumps({"user_id": str(user_id)}).encode()
    )

    assert snapshot.is_active is False
    assert snapshot.deleted is True


def test_parse_user_event_snapshot_requires_role_on_role_changed() -> None:
    with pytest.raises(ValueError):
        _parse_user_event_snapshot(
            "user.role_changed.v1",
            json.dumps({"user_id": str(uuid.uuid4())}).encode(),
        )
