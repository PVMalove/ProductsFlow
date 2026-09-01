from kernel_domain.domain_event import DomainEvent
from kernel_platform.outbox.models import OutboxMessage
from sqlalchemy.ext.asyncio import AsyncSession

from domain.ticket import Ticket
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


def _to_outbox(event: DomainEvent) -> OutboxMessage:
    from domain.events.ticket_created import TicketCreated

    assert isinstance(event, TicketCreated)
    return OutboxMessage(
        aggregate_type="Ticket",
        aggregate_id=event.ticket_id,
        event_type=event.event_type,
        payload={"ticket_id": str(event.ticket_id), "author_id": str(event.author_id)},
        occurred_at=event.occurred_on_utc,
    )


SqlTicketRepository = TicketRepository
