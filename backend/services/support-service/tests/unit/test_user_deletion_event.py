import json
import uuid
from types import SimpleNamespace

import pytest

from api.worker import _message_id, _parse_deleted_user_event, handle_user_event
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


@pytest.mark.asyncio
async def test_worker_acks_other_valid_user_events_without_support_mutation() -> None:
    await handle_user_event(
        _message(  # type: ignore[arg-type]
            body=json.dumps({"user_id": str(uuid.uuid4())}).encode(),
            event_type="user.registered.v1",
        ),
        None,  # type: ignore[arg-type]
    )
