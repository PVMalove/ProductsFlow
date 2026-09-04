"""Интеграционные тесты транзакционной оболочки `SupportUnitOfWork`
(ADR 0006, issue #245) — доказывают атомарность/rollback/outbox-drain
поведение самого UoW, независимо от бизнес-логики какого-либо конкретного
command handler'а (реальный Postgres, существующая SAVEPOINT-фикстура /
настоящее второе соединение, где нужно наблюдать межтранзакционную
видимость)."""

import uuid
from collections.abc import AsyncIterator

import pytest
import pytest_asyncio
from kernel_platform.outbox.models import Base, OutboxMessage
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncEngine, AsyncSession, async_sessionmaker

from application.commands import CreateTicketCommand, CreateTicketCommandHandler
from domain.entities.ticket import Ticket, TicketClosedError
from domain.ticket_status import TicketStatus
from domain.value_objects.ticket_id import TicketId
from infrastructure.db.entity_configurations.models import (
    TicketMessageModel,
    TicketModel,
)
from infrastructure.db.unit_of_work import SqlSupportUnitOfWork

pytestmark = pytest.mark.asyncio(loop_scope="session")


@pytest_asyncio.fixture(scope="session", loop_scope="session", autouse=True)
async def support_schema(db_engine: AsyncEngine) -> AsyncIterator[None]:
    async with db_engine.begin() as connection:
        await connection.run_sync(Base.metadata.create_all)
    try:
        yield
    finally:
        async with db_engine.begin() as connection:
            await connection.run_sync(Base.metadata.drop_all)


async def test_two_mutating_calls_commit_as_one_atomic_transaction(
    db_engine: AsyncEngine,
) -> None:
    """Handler с 2+ мутирующими вызовами репозитория должен коммититься как
    одна транзакция: невидима другим соединениям до `uow.commit()`, затем
    обе мутации и обе строки outbox видны вместе."""
    session_factory = async_sessionmaker(db_engine, expire_on_commit=False)
    author_id = uuid.uuid4()

    async def read_ticket(ticket_id: TicketId) -> TicketModel | None:
        async with session_factory() as session:
            return await session.get(TicketModel, ticket_id.value)

    async with session_factory() as write_session:
        uow = SqlSupportUnitOfWork(write_session)
        async with uow:
            ticket = await uow.tickets.create(
                Ticket.create(
                    author_id=author_id, subject="Subject", first_message="First"
                ).value
            )
            assert await read_ticket(ticket.id) is None

            await uow.tickets.add_message(
                ticket_id=ticket.id, actor_id=author_id, body="Second", is_admin=False
            )
            assert await read_ticket(ticket.id) is None

            await uow.commit()

    assert await read_ticket(ticket.id) is not None
    async with session_factory() as session:
        messages = list(
            (
                await session.scalars(
                    select(TicketMessageModel).where(
                        TicketMessageModel.ticket_id == ticket.id.value
                    )
                )
            ).all()
        )
        outbox_types = [
            row.event_type
            for row in (
                await session.scalars(
                    select(OutboxMessage)
                    .where(OutboxMessage.aggregate_id == ticket.id.value)
                    .order_by(OutboxMessage.id)
                )
            ).all()
        ]
    assert len(messages) == 2
    assert outbox_types == ["ticket.created.v1", "ticket.message_added.v1"]


async def test_failure_mid_transaction_leaves_no_partial_state_or_outbox_row(
    db_session: AsyncSession,
) -> None:
    """Отказ внутри транзакции откатывает всё из этой транзакции — включая
    мутацию, которая сама по себе прошла успешно — а не только вызов,
    поднявший исключение."""
    author_id = uuid.uuid4()
    uow = SqlSupportUnitOfWork(db_session)

    closed_ticket = Ticket.create(
        author_id=author_id, subject="Closed subject", first_message="First"
    ).value
    async with uow:
        await uow.tickets.create(closed_ticket)
        await uow.commit()
    next_statuses = (
        TicketStatus.IN_PROGRESS,
        TicketStatus.RESOLVED,
        TicketStatus.CLOSED,
    )
    for status in next_statuses:
        async with uow:
            await uow.tickets.change_status(
                ticket_id=closed_ticket.id, actor_id=author_id, status=status
            )
            await uow.commit()

    new_ticket_id: TicketId | None = None
    async with uow:
        new_ticket = await uow.tickets.create(
            Ticket.create(
                author_id=author_id, subject="New subject", first_message="Hello"
            ).value
        )
        new_ticket_id = new_ticket.id
        with pytest.raises(TicketClosedError):
            await uow.tickets.add_message(
                ticket_id=closed_ticket.id,
                actor_id=author_id,
                body="Too late",
                is_admin=False,
            )
        # явного commit нет — rollback-by-default откатывает и create() выше тоже

    assert new_ticket_id is not None
    assert await db_session.get(TicketModel, new_ticket_id.value) is None
    outbox_for_new_ticket = await db_session.scalar(
        select(OutboxMessage).where(OutboxMessage.aggregate_id == new_ticket_id.value)
    )
    assert outbox_for_new_ticket is None


async def test_happy_path_still_writes_the_expected_outbox_row(
    db_session: AsyncSession,
) -> None:
    handler = CreateTicketCommandHandler(SqlSupportUnitOfWork(db_session))
    author_id = uuid.uuid4()

    result = await handler.execute(
        CreateTicketCommand(
            author_id=author_id, subject="Subject", first_message="Message"
        )
    )

    assert result.is_ok
    outbox = await db_session.scalar(
        select(OutboxMessage).where(OutboxMessage.aggregate_id == result.value.id)
    )
    assert outbox is not None
    assert outbox.event_type == "ticket.created.v1"
