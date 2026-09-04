import uuid
from datetime import UTC, datetime

import pytest
from kernel_platform.outbox.models import OutboxMessage

from domain.entities.ticket import (
    InvalidStatusTransitionError,
    Ticket,
    TicketClosedError,
    TicketMessageImmutableError,
)
from domain.ticket_status import TicketStatus
from domain.value_objects.ticket_id import TicketId
from infrastructure.db.entity_configurations.models import (
    TicketMessageModel,
    TicketModel,
)
from infrastructure.db.ticket_repository import SqlTicketRepository


class RecordingSession:
    def __init__(self) -> None:
        self.added: list[object] = []
        self.rolled_back = False

    def add(self, value: object) -> None:
        self.added.append(value)

    async def flush(self) -> None:
        pass

    async def rollback(self) -> None:
        self.rolled_back = True


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
    ).value

    await SqlTicketRepository(session).create(ticket)  # type: ignore[arg-type]

    assert {type(item).__name__ for item in session.added} == {
        "TicketModel",
        "TicketMessageModel",
        "OutboxMessage",
    }


def _stored_ticket(
    author_id: uuid.UUID,
    *,
    status: TicketStatus = TicketStatus.OPEN,
    is_system: bool = False,
) -> tuple[TicketModel, TicketMessageModel]:
    ticket_id = uuid.uuid4()
    created_at = datetime.now(UTC)
    return (
        TicketModel(
            id=ticket_id,
            author_id=author_id,
            subject="Subject",
            status=status.value,
            created_at=created_at,
        ),
        TicketMessageModel(
            id=uuid.uuid4(),
            ticket_id=ticket_id,
            author_id=author_id,
            body="First message",
            created_at=created_at,
            is_system=is_system,
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
        ticket_id=TicketId.create(row.id),
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
        ticket_id=TicketId.create(row.id),
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
        ticket_id=TicketId.create(row.id),
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
        ticket_id=TicketId.create(row.id),
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

    with pytest.raises(InvalidStatusTransitionError):
        await SqlTicketRepository(session).change_status(  # type: ignore[arg-type]
            ticket_id=TicketId.create(row.id),
            actor_id=uuid.uuid4(),
            status=TicketStatus.RESOLVED,
        )

    assert session.added == []
    assert session.rolled_back is True


@pytest.mark.asyncio
async def test_add_message_on_closed_ticket_raises_and_rolls_back() -> None:
    author_id = uuid.uuid4()
    row, first_message = _stored_ticket(author_id, status=TicketStatus.CLOSED)
    session = MutationSession(row, first_message)

    with pytest.raises(TicketClosedError):
        await SqlTicketRepository(session).add_message(  # type: ignore[arg-type]
            ticket_id=TicketId.create(row.id),
            actor_id=author_id,
            body="Too late",
            is_admin=False,
        )

    assert session.added == []
    assert session.rolled_back is True


@pytest.mark.asyncio
async def test_edit_message_on_system_message_raises_and_rolls_back() -> None:
    author_id = uuid.uuid4()
    row, message = _stored_ticket(author_id, is_system=True)
    session = MutationSession(row, message)

    with pytest.raises(TicketMessageImmutableError):
        await SqlTicketRepository(session).edit_message(  # type: ignore[arg-type]
            ticket_id=TicketId.create(row.id),
            message_id=message.id,
            actor_id=author_id,
            body="Should not apply",
        )  # type: ignore[arg-type]

    assert session.added == []
    assert session.rolled_back is True
