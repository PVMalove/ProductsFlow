import uuid
from datetime import UTC, datetime

import pytest
from kernel_platform.outbox.models import OutboxMessage

from domain.ticket import Ticket, TicketStatus
from infrastructure.db.entity_configurations.models import (
    TicketMessageModel,
    TicketModel,
)
from infrastructure.db.ticket_repository import SqlTicketRepository


class RecordingSession:
    def __init__(self) -> None:
        self.added: list[object] = []

    def add(self, value: object) -> None:
        self.added.append(value)

    async def flush(self) -> None:
        pass


class MutationSession(RecordingSession):
    def __init__(self, ticket: TicketModel, message: TicketMessageModel) -> None:
        super().__init__()
        self.ticket = ticket
        self.message = message

    async def scalar(self, statement: object) -> TicketModel:
        return self.ticket

    async def scalars(self, statement: object) -> object:
        class Result:
            def all(_inner_self: object) -> list[TicketMessageModel]:
                return [self.message]

        return Result()


@pytest.mark.asyncio
async def test_create_adds_ticket_message_and_outbox_without_committing() -> None:
    session = RecordingSession()
    ticket = Ticket.create(
        author_id=uuid.uuid4(), subject="Subject", first_message="Message"
    )

    await SqlTicketRepository(session).create(ticket)  # type: ignore[arg-type]

    assert {type(item).__name__ for item in session.added} == {
        "TicketModel",
        "TicketMessageModel",
        "OutboxMessage",
    }


def _stored_ticket(author_id: uuid.UUID) -> tuple[TicketModel, TicketMessageModel]:
    ticket_id = uuid.uuid4()
    created_at = datetime.now(UTC)
    return (
        TicketModel(
            id=ticket_id,
            author_id=author_id,
            subject="Subject",
            status=TicketStatus.OPEN.value,
            created_at=created_at,
        ),
        TicketMessageModel(
            id=uuid.uuid4(),
            ticket_id=ticket_id,
            author_id=author_id,
            body="First message",
            created_at=created_at,
        ),
    )


@pytest.mark.asyncio
async def test_add_message_writes_only_technical_outbox_data_without_committing() -> (
    None
):
    author_id = uuid.uuid4()
    row, first_message = _stored_ticket(author_id)
    session = MutationSession(row, first_message)

    result = await SqlTicketRepository(session).add_message(  # type: ignore[arg-type]
        ticket_id=row.id,
        actor_id=uuid.uuid4(),
        body="Reply text",
        is_admin=True,
    )

    assert result is not None
    assert row.status == TicketStatus.OPEN.value
    outbox = [item for item in session.added if isinstance(item, OutboxMessage)]
    assert len(outbox) == 1
    assert outbox[0].event_type == "ticket.message_added.v1"
    assert "body" not in outbox[0].payload


@pytest.mark.asyncio
async def test_edit_message_updates_body_and_writes_technical_outbox_event() -> None:
    author_id = uuid.uuid4()
    row, message = _stored_ticket(author_id)
    session = MutationSession(row, message)

    result = await SqlTicketRepository(session).edit_message(  # type: ignore[arg-type]
        ticket_id=row.id,
        message_id=message.id,
        actor_id=author_id,
        body="Corrected text",
    )  # type: ignore[arg-type]

    assert result is not None
    assert message.body == "Corrected text"
    outbox = [item for item in session.added if isinstance(item, OutboxMessage)]
    assert len(outbox) == 1
    assert outbox[0].event_type == "ticket.message_edited.v1"
    assert "body" not in outbox[0].payload


@pytest.mark.asyncio
async def test_admin_delete_soft_deletes_message_and_writes_technical_event() -> None:
    author_id = uuid.uuid4()
    row, message = _stored_ticket(author_id)
    session = MutationSession(row, message)

    result = await SqlTicketRepository(session).delete_message(  # type: ignore[arg-type]
        ticket_id=row.id,
        message_id=message.id,
        actor_id=uuid.uuid4(),
        is_admin=True,
    )  # type: ignore[arg-type]

    assert result is not None
    assert message.body == "[Сообщение удалено]"
    assert message.is_deleted is True
    outbox = [item for item in session.added if isinstance(item, OutboxMessage)]
    assert len(outbox) == 1
    assert outbox[0].event_type == "ticket.message_deleted.v1"
    assert "body" not in outbox[0].payload


@pytest.mark.asyncio
async def test_editing_message_on_another_ticket_owner_is_hidden() -> None:
    author_id = uuid.uuid4()
    row, message = _stored_ticket(author_id)
    session = MutationSession(row, message)

    result = await SqlTicketRepository(session).edit_message(  # type: ignore[arg-type]
        ticket_id=row.id,
        message_id=message.id,
        actor_id=uuid.uuid4(),
        body="Should not be visible",
    )  # type: ignore[arg-type]

    assert result is None
    assert message.body == "First message"
    assert session.added == []


@pytest.mark.asyncio
async def test_rejected_status_change_raises_without_mutating_session() -> None:
    author_id = uuid.uuid4()
    row, first_message = _stored_ticket(author_id)
    session = MutationSession(row, first_message)

    with pytest.raises(ValueError):
        await SqlTicketRepository(session).change_status(  # type: ignore[arg-type]
            ticket_id=row.id,
            actor_id=uuid.uuid4(),
            status=TicketStatus.RESOLVED,
        )

    assert session.added == []
