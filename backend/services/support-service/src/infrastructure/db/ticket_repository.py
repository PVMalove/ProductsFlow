import uuid

from kernel_domain.domain_event import DomainEvent
from kernel_platform.outbox.models import OutboxMessage
from sqlalchemy import Select, select, tuple_
from sqlalchemy.ext.asyncio import AsyncSession

from domain.events import TicketMessageAdded, TicketStatusChanged
from domain.message import TicketMessage
from domain.repositories import Cursor, MessagePage, PageInfo, TicketPage
from domain.ticket import Ticket, TicketStatus
from infrastructure.db.models import TicketMessageModel, TicketModel


class TicketRepository:
    def __init__(self, session: AsyncSession) -> None:
        self._session = session

    async def create(self, ticket: Ticket) -> Ticket:
        self._session.add(
            TicketModel(
                id=ticket.id,
                author_id=ticket.author_id,
                subject=ticket.subject,
                status=ticket.status.value,
            )
        )
        await self._session.flush()
        for message in ticket.messages:
            self._session.add(
                TicketMessageModel(
                    id=message.id,
                    ticket_id=message.ticket_id,
                    author_id=message.author_id,
                    body=message.body,
                    created_at=message.created_at,
                    is_system=message.is_system,
                )
            )
        for event in ticket.pull_events():
            self._session.add(_to_outbox(event))
        await self._session.commit()
        return ticket

    async def add_message(
        self,
        *,
        ticket_id: uuid.UUID,
        actor_id: uuid.UUID,
        body: str,
        is_admin: bool,
    ) -> Ticket | None:
        row = await self._load_for_update(ticket_id)
        if row is None or (not is_admin and row.author_id != actor_id):
            await self._session.rollback()
            return None

        ticket = await self._to_domain(row)
        try:
            message = ticket.add_message(
                author_id=actor_id,
                body=body,
                actor_category="admin" if is_admin else "user",
            )
            row.status = ticket.status.value
            self._session.add(
                TicketMessageModel(
                    id=message.id,
                    ticket_id=message.ticket_id,
                    author_id=message.author_id,
                    body=message.body,
                    created_at=message.created_at,
                    is_system=message.is_system,
                )
            )
            await self._drain_outbox(ticket)
            await self._session.commit()
        except Exception:
            await self._session.rollback()
            raise
        return ticket

    async def change_status(
        self, *, ticket_id: uuid.UUID, actor_id: uuid.UUID, status: TicketStatus
    ) -> Ticket | None:
        row = await self._load_for_update(ticket_id)
        if row is None:
            await self._session.rollback()
            return None

        ticket = await self._to_domain(row)
        try:
            ticket.change_status(status, actor_category="admin")
            row.status = ticket.status.value
            await self._drain_outbox(ticket)
            await self._session.commit()
        except Exception:
            await self._session.rollback()
            raise
        return ticket

    async def get_for_author(
        self, ticket_id: uuid.UUID, author_id: uuid.UUID
    ) -> Ticket | None:
        row = await self._session.scalar(
            select(TicketModel).where(
                TicketModel.id == ticket_id, TicketModel.author_id == author_id
            )
        )
        return await self._to_domain(row) if row is not None else None

    async def get_by_id(self, ticket_id: uuid.UUID) -> Ticket | None:
        row = await self._session.get(TicketModel, ticket_id)
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
        ticket_id: uuid.UUID,
        limit: int,
        after: Cursor | None = None,
        before: Cursor | None = None,
    ) -> MessagePage:
        stmt = select(TicketMessageModel).where(
            TicketMessageModel.ticket_id == ticket_id
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
                TicketMessage(
                    id=row.id,
                    ticket_id=row.ticket_id,
                    author_id=row.author_id,
                    body=row.body,
                    created_at=row.created_at,
                    is_system=row.is_system,
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
        return Ticket(
            row.id,
            author_id=row.author_id,
            subject=row.subject,
            status=TicketStatus(row.status),
            messages=[
                TicketMessage(
                    id=message.id,
                    ticket_id=message.ticket_id,
                    author_id=message.author_id,
                    body=message.body,
                    created_at=message.created_at,
                    is_system=message.is_system,
                )
                for message in messages
            ],
            created_at=row.created_at,
        )

    async def _load_for_update(self, ticket_id: uuid.UUID) -> TicketModel | None:
        statement = (
            select(TicketModel)
            .where(TicketModel.id == ticket_id)
            .with_for_update()
        )
        return await self._session.scalar(statement)

    async def _drain_outbox(self, ticket: Ticket) -> None:
        for event in ticket.pull_events():
            self._session.add(_to_outbox(event))


def _to_outbox(event: DomainEvent) -> OutboxMessage:
    from domain.events.ticket_created import TicketCreated

    if isinstance(event, TicketCreated):
        payload = {
            "ticket_id": str(event.ticket_id),
            "author_id": str(event.author_id),
        }
    elif isinstance(event, TicketMessageAdded):
        payload = {
            "ticket_id": str(event.ticket_id),
            "message_id": str(event.message_id),
            "actor_category": event.actor_category,
        }
    elif isinstance(event, TicketStatusChanged):
        payload = {
            "ticket_id": str(event.ticket_id),
            "previous_status": event.previous_status,
            "status": event.status,
            "actor_category": event.actor_category,
        }
    else:
        raise TypeError(f"unsupported ticket event: {type(event).__name__}")
    return OutboxMessage(
        aggregate_type="Ticket",
        aggregate_id=event.ticket_id,
        event_type=event.event_type,
        payload=payload,
        occurred_at=event.occurred_on_utc,
    )


SqlTicketRepository = TicketRepository
