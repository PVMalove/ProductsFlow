# ruff: noqa: E501
from typing import Any

from kernel_domain.entity import Entity
from sqlalchemy.ext.asyncio import AsyncSession

from kernel_platform.outbox.models import OutboxMessage
from kernel_platform.outbox.trace_context import serialize_trace_context


async def drain_events_to_outbox(session: AsyncSession, entity: Entity[Any]) -> None:
    """Дренирует накопленные доменные события агрегата в строки Outbox той
    же сессии (ADR 0006/0010) — единственное, что видит и домен, и `AsyncSession`,
    остаётся у вызывающего репозитория: он передаёт сюда сессию и агрегат,
    сам не зная ничего о конкретных подклассах события. Строки добавляются
    в сессию, но не коммитятся — коммит транзакции остаётся за вызывающим,
    вместе с его собственной мутацией агрегата.

    Args:
        session (AsyncSession): Сессия, в которую добавляются строки Outbox
            — та же, в которой вызывающий коммитит свою мутацию агрегата.
        entity (Entity[Any]): Агрегат, чьи накопленные события забираются
            через `pull_events()` и мапятся по контракту `DomainEvent`."""
    for event in entity.pull_events():
        session.add(
            OutboxMessage(
                aggregate_type=event.aggregate_type,
                aggregate_id=event.aggregate_id(),
                event_type=event.event_type,
                payload=event.to_payload(),
                occurred_at=event.occurred_on_utc,
                trace_context=serialize_trace_context(),
            )
        )
