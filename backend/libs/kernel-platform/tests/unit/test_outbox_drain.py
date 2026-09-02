# ruff: noqa: E501
import uuid
from dataclasses import dataclass
from datetime import datetime
from typing import Any

from kernel_domain.domain_event import DomainEvent
from kernel_domain.entity import Entity

from kernel_platform.outbox.drain import drain_events_to_outbox
from kernel_platform.outbox.models import OutboxMessage


@dataclass(frozen=True, kw_only=True)
class _WidgetCreated(DomainEvent):
    event_type: str = "widget.created.v1"
    aggregate_type: str = "Widget"

    widget_id: uuid.UUID
    name: str

    def aggregate_id(self) -> uuid.UUID:
        return self.widget_id

    def to_payload(self) -> dict[str, Any]:
        return {"widget_id": str(self.widget_id), "name": self.name}


class _Widget(Entity[uuid.UUID]):
    def create(self, name: str) -> None:
        self.add_domain_event(_WidgetCreated(widget_id=self.id, name=name))


class _RecordingSession:
    def __init__(self) -> None:
        self.added: list[object] = []

    def add(self, value: object) -> None:
        self.added.append(value)


async def test_drain_events_to_outbox_maps_each_event_via_the_domain_event_contract() -> (
    None
):
    widget = _Widget(uuid.uuid4())
    widget.create("Widget")
    session = _RecordingSession()

    await drain_events_to_outbox(session, widget)  # type: ignore[arg-type]

    assert len(session.added) == 1
    row = session.added[0]
    assert isinstance(row, OutboxMessage)
    assert row.aggregate_type == "Widget"
    assert row.aggregate_id == widget.id
    assert row.event_type == "widget.created.v1"
    assert row.payload == {"widget_id": str(widget.id), "name": "Widget"}
    assert isinstance(row.occurred_at, datetime)


async def test_drain_events_to_outbox_drains_the_aggregate_event_queue() -> None:
    widget = _Widget(uuid.uuid4())
    widget.create("Widget")
    session = _RecordingSession()

    await drain_events_to_outbox(session, widget)  # type: ignore[arg-type]

    assert widget.pull_events() == []


async def test_drain_events_to_outbox_adds_nothing_for_an_aggregate_without_events() -> (
    None
):
    widget = _Widget(uuid.uuid4())
    session = _RecordingSession()

    await drain_events_to_outbox(session, widget)  # type: ignore[arg-type]

    assert session.added == []


async def test_drain_events_to_outbox_maps_every_event_when_several_were_raised() -> (
    None
):
    widget = _Widget(uuid.uuid4())
    widget.create("First")
    widget.add_domain_event(_WidgetCreated(widget_id=widget.id, name="Second"))
    session = _RecordingSession()

    await drain_events_to_outbox(session, widget)  # type: ignore[arg-type]

    assert [row.payload["name"] for row in session.added] == ["First", "Second"]  # type: ignore[attr-defined]
