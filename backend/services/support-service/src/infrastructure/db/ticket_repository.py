import uuid
from typing import NoReturn

from kernel_domain.domain_event import DomainEvent
from kernel_domain.errors import Error
from kernel_platform.outbox.models import OutboxMessage
from sqlalchemy import Select, select, tuple_
from sqlalchemy.dialects.postgresql import insert
from sqlalchemy.ext.asyncio import AsyncSession

from domain.entities.ticket import (
    InvalidStatusTransitionError,
    Ticket,
    TicketClosedError,
    TicketMessageAlreadyDeletedError,
    TicketMessageImmutableError,
    TicketMessageNotFoundError,
)
from domain.entities.ticket_message import TicketMessage
from domain.events import (
    TicketMessageAdded,
    TicketMessageDeleted,
    TicketMessageEdited,
    TicketStatusChanged,
)
from domain.repositories import Cursor, MessagePage, PageInfo, TicketPage
from domain.ticket_status import TicketStatus
from domain.value_objects.ticket_id import TicketId
from infrastructure.db.entity_configurations.models import (
    ProcessedMessage,
    TicketMessageModel,
    TicketModel,
)


def _raise_for_error(error: Error) -> NoReturn:
    """Трансляционный шов (issue #253): переводит `Result.fail` доменных
    методов `Ticket` обратно в те же типизированные исключения, что они
    бросали раньше напрямую, — внешний HTTP-контракт не меняется."""
    if error.code == "ticket_closed":
        raise TicketClosedError(error.description)
    if error.code == "invalid_status_transition":
        raise InvalidStatusTransitionError(error.description)
    if error.code == "message_not_found":
        raise TicketMessageNotFoundError(error.description)
    if error.code == "message_immutable":
        raise TicketMessageImmutableError(error.description)
    if error.code == "message_already_deleted":
        raise TicketMessageAlreadyDeletedError(error.description)
    raise ValueError(error.description)


class TicketRepository:
    def __init__(self, session: AsyncSession) -> None:
        self._session = session

    async def create(self, ticket: Ticket) -> Ticket:
        self._session.add(
            TicketModel(
                id=ticket.id.value,
                author_id=ticket.author_id,
                subject=ticket.subject,
                status=ticket.status.value,
            )
        )
        await self._session.flush()
        for message in ticket.messages:
            self._session.add(_to_message_model(message))
        for event in ticket.pull_events():
            self._session.add(_to_outbox(event))
        return ticket

    async def process_user_deleted(
        self, *, message_id: int, user_id: uuid.UUID
    ) -> bool:
        """Apply one identity deletion atomically and idempotently."""
        inserted_id = await self._session.scalar(
            insert(ProcessedMessage)
            .values(message_id=message_id)
            .on_conflict_do_nothing()
            .returning(ProcessedMessage.message_id)
        )
        if inserted_id is None:
            return False

        ticket_rows = list(
            (
                await self._session.scalars(
                    select(TicketModel)
                    .where(TicketModel.author_id == user_id)
                    .with_for_update()
                )
            ).all()
        )
        for row in ticket_rows:
            ticket = await self._to_domain(row)
            ticket.anonymize_deleted_user(user_id)
            row.author_id = ticket.author_id
            row.status = ticket.status.value
            message_rows = list(
                (
                    await self._session.scalars(
                        select(TicketMessageModel).where(
                            TicketMessageModel.ticket_id == ticket.id.value
                        )
                    )
                ).all()
            )
            existing_rows = {message.id: message for message in message_rows}
            for message in ticket.messages:
                message_row = existing_rows.get(message.id)
                if message_row is None:
                    self._session.add(_to_message_model(message))
                else:
                    message_row.author_id = message.author_id
            await self._drain_outbox(ticket)
        return True

    async def add_message(
        self,
        *,
        ticket_id: TicketId,
        actor_id: uuid.UUID,
        body: str,
        is_admin: bool,
    ) -> Ticket | None:
        row = await self._load_for_update(ticket_id)
        if row is None or (not is_admin and row.author_id != actor_id):
            return None

        ticket = await self._to_domain(row)
        result = ticket.add_message(
            author_id=actor_id,
            body=body,
            actor_category="admin" if is_admin else "user",
        )
        if result.is_err:
            await self._session.rollback()
            _raise_for_error(result.error)
        row.status = ticket.status.value
        self._session.add(_to_message_model(result.value))
        await self._drain_outbox(ticket)
        return ticket

    async def change_status(
        self, *, ticket_id: TicketId, actor_id: uuid.UUID, status: TicketStatus
    ) -> Ticket | None:
        row = await self._load_for_update(ticket_id)
        if row is None:
            return None

        ticket = await self._to_domain(row)
        result = ticket.change_status(status, actor_category="admin")
        if result.is_err:
            await self._session.rollback()
            _raise_for_error(result.error)
        row.status = ticket.status.value
        await self._drain_outbox(ticket)
        return ticket

    async def edit_message(
        self,
        *,
        ticket_id: TicketId,
        message_id: uuid.UUID,
        actor_id: uuid.UUID,
        body: str,
        is_admin: bool = False,
    ) -> Ticket | None:
        ticket_row = await self._load_for_update(ticket_id)
        if ticket_row is None or (not is_admin and ticket_row.author_id != actor_id):
            return None
        message_row = await self._load_message(ticket_id, message_id)
        if message_row is None or message_row.author_id != actor_id:
            return None

        ticket = await self._to_domain(ticket_row)
        result = ticket.edit_message(
            message_id=message_id,
            author_id=actor_id,
            body=body,
            actor_category="admin" if is_admin else "user",
        )
        if result.is_err:
            await self._session.rollback()
            _raise_for_error(result.error)
        message_row.body = result.value.body
        await self._drain_outbox(ticket)
        return ticket

    async def delete_message(
        self,
        *,
        ticket_id: TicketId,
        message_id: uuid.UUID,
        actor_id: uuid.UUID,
        is_admin: bool,
    ) -> Ticket | None:
        ticket_row = await self._load_for_update(ticket_id)
        if ticket_row is None or (not is_admin and ticket_row.author_id != actor_id):
            return None
        message_row = await self._load_message(ticket_id, message_id)
        if message_row is None:
            return None

        ticket = await self._to_domain(ticket_row)
        result = ticket.delete_message(
            message_id=message_id,
            actor_id=actor_id,
            actor_category="admin" if is_admin else "user",
        )
        if result.is_err:
            await self._session.rollback()
            _raise_for_error(result.error)
        message_row.body = result.value.body
        message_row.is_deleted = result.value.is_deleted
        await self._drain_outbox(ticket)
        return ticket

    async def get_for_author(
        self, ticket_id: TicketId, author_id: uuid.UUID
    ) -> Ticket | None:
        row = await self._session.scalar(
            select(TicketModel).where(
                TicketModel.id == ticket_id.value, TicketModel.author_id == author_id
            )
        )
        return await self._to_domain(row) if row is not None else None

    async def get_by_id(self, ticket_id: TicketId) -> Ticket | None:
        row = await self._session.get(TicketModel, ticket_id.value)
        return await self._to_domain(row) if row is not None else None

    async def list_for_author(
        self,
        *,
        author_id: uuid.UUID,
        limit: int,
        after: Cursor | None = None,
        before: Cursor | None = None,
    ) -> TicketPage:
        return await self._list(
            select(TicketModel).where(TicketModel.author_id == author_id),
            limit=limit,
            after=after,
            before=before,
        )

    async def list_all(
        self,
        *,
        limit: int,
        after: Cursor | None = None,
        before: Cursor | None = None,
    ) -> TicketPage:
        return await self._list(
            select(TicketModel), limit=limit, after=after, before=before
        )

    async def list_messages(
        self,
        *,
        ticket_id: TicketId,
        limit: int,
        after: Cursor | None = None,
        before: Cursor | None = None,
    ) -> MessagePage:
        stmt = select(TicketMessageModel).where(
            TicketMessageModel.ticket_id == ticket_id.value
        )
        if before is not None:
            stmt = stmt.where(
                tuple_(TicketMessageModel.created_at, TicketMessageModel.id)
                < (before.created_at, before.id)
            ).order_by(
                TicketMessageModel.created_at.desc(), TicketMessageModel.id.desc()
            )
            has_prev = True
        else:
            if after is not None:
                stmt = stmt.where(
                    tuple_(TicketMessageModel.created_at, TicketMessageModel.id)
                    > (after.created_at, after.id)
                )
            stmt = stmt.order_by(
                TicketMessageModel.created_at.asc(), TicketMessageModel.id.asc()
            )
            has_prev = after is not None
        rows = list((await self._session.scalars(stmt.limit(limit + 1))).all())
        has_more = len(rows) > limit
        rows = rows[:limit]
        if before is not None:
            rows.reverse()
        if not rows:
            return MessagePage([], PageInfo(None, None, False, False))
        from application.pagination import encode_cursor

        return MessagePage(
            [
                TicketMessage.reconstitute(
                    id=row.id,
                    ticket_id=TicketId.create(row.ticket_id),
                    author_id=row.author_id,
                    body=row.body,
                    created_at=row.created_at,
                    is_system=row.is_system,
                    is_deleted=row.is_deleted,
                )
                for row in rows
            ],
            PageInfo(
                encode_cursor(rows[-1].created_at, rows[-1].id) if has_more else None,
                encode_cursor(rows[0].created_at, rows[0].id) if has_prev else None,
                has_more,
                has_prev,
            ),
        )

    async def _list(
        self,
        statement: Select[tuple[TicketModel]],
        *,
        limit: int,
        after: Cursor | None,
        before: Cursor | None,
    ) -> TicketPage:
        stmt = statement
        if before is not None:
            stmt = stmt.where(
                tuple_(TicketModel.created_at, TicketModel.id)
                > (before.created_at, before.id)
            )
            stmt = stmt.order_by(TicketModel.created_at.asc(), TicketModel.id.asc())
            rows = list((await self._session.scalars(stmt.limit(limit + 1))).all())
            has_more = len(rows) > limit
            rows = rows[:limit]
            rows.reverse()
            has_prev = has_more
        else:
            if after is not None:
                stmt = stmt.where(
                    tuple_(TicketModel.created_at, TicketModel.id)
                    < (after.created_at, after.id)
                )
            stmt = stmt.order_by(TicketModel.created_at.desc(), TicketModel.id.desc())
            rows = list((await self._session.scalars(stmt.limit(limit + 1))).all())
            has_more = len(rows) > limit
            rows = rows[:limit]
            has_prev = after is not None
        if not rows:
            return TicketPage([], PageInfo(None, None, False, False))
        items = [await self._to_domain(row) for row in rows]
        from application.pagination import encode_cursor

        return TicketPage(
            items,
            PageInfo(
                next_cursor=encode_cursor(rows[-1].created_at, rows[-1].id)
                if has_more
                else None,
                prev_cursor=encode_cursor(rows[0].created_at, rows[0].id)
                if has_prev
                else None,
                has_more=has_more,
                has_prev=has_prev,
            ),
        )

    async def _to_domain(self, row: TicketModel) -> Ticket:
        messages = list(
            (
                await self._session.scalars(
                    select(TicketMessageModel)
                    .where(TicketMessageModel.ticket_id == row.id)
                    .order_by(
                        TicketMessageModel.created_at.asc(), TicketMessageModel.id.asc()
                    )
                )
            ).all()
        )
        return Ticket.reconstitute(
            TicketId.create(row.id),
            author_id=row.author_id,
            subject=row.subject,
            status=TicketStatus(row.status),
            messages=[
                TicketMessage.reconstitute(
                    id=message.id,
                    ticket_id=TicketId.create(message.ticket_id),
                    author_id=message.author_id,
                    body=message.body,
                    created_at=message.created_at,
                    is_system=message.is_system,
                    is_deleted=message.is_deleted,
                )
                for message in messages
            ],
            created_at=row.created_at,
        )

    async def _load_for_update(self, ticket_id: TicketId) -> TicketModel | None:
        statement = (
            select(TicketModel)
            .where(TicketModel.id == ticket_id.value)
            .with_for_update()
        )
        return await self._session.scalar(statement)

    async def _load_message(
        self, ticket_id: TicketId, message_id: uuid.UUID
    ) -> TicketMessageModel | None:
        result = await self._session.scalars(
            select(TicketMessageModel).where(
                TicketMessageModel.ticket_id == ticket_id.value,
                TicketMessageModel.id == message_id,
            )
        )
        rows = list(result.all())
        return rows[0] if rows else None

    async def _drain_outbox(self, ticket: Ticket) -> None:
        for event in ticket.pull_events():
            self._session.add(_to_outbox(event))


def _to_outbox(event: DomainEvent) -> OutboxMessage:
    from domain.events.ticket_domain_event import TicketCreated

    if isinstance(event, TicketCreated):
        payload = {
            "ticket_id": str(event.ticket_id.value),
            "author_id": str(event.author_id),
        }
    elif isinstance(event, TicketMessageAdded):
        payload = {
            "ticket_id": str(event.ticket_id.value),
            "message_id": str(event.message_id),
            "actor_category": event.actor_category,
        }
    elif isinstance(event, TicketMessageEdited):
        payload = {
            "ticket_id": str(event.ticket_id.value),
            "message_id": str(event.message_id),
            "actor_category": event.actor_category,
        }
    elif isinstance(event, TicketMessageDeleted):
        payload = {
            "ticket_id": str(event.ticket_id.value),
            "message_id": str(event.message_id),
            "actor_category": event.actor_category,
        }
    elif isinstance(event, TicketStatusChanged):
        payload = {
            "ticket_id": str(event.ticket_id.value),
            "previous_status": event.previous_status,
            "status": event.status,
            "actor_category": event.actor_category,
        }
    else:
        raise TypeError(f"unsupported ticket event: {type(event).__name__}")
    return OutboxMessage(
        aggregate_type="Ticket",
        aggregate_id=event.ticket_id.value,
        event_type=event.event_type,
        payload=payload,
        occurred_at=event.occurred_on_utc,
    )


SqlTicketRepository = TicketRepository


def _to_message_model(message: TicketMessage) -> TicketMessageModel:
    return TicketMessageModel(
        id=message.id,
        ticket_id=message.ticket_id.value,
        author_id=message.author_id,
        body=message.body,
        created_at=message.created_at,
        is_system=message.is_system,
        is_deleted=message.is_deleted,
    )
