import uuid
from dataclasses import dataclass
from datetime import UTC, datetime

from kernel_domain.domain_event import DomainEvent


def test_domain_event_gets_a_unique_id_and_utc_occurrence_timestamp() -> None:
    event = DomainEvent()

    assert isinstance(event.id, uuid.UUID)
    assert isinstance(event.occurred_on_utc, datetime)
    assert event.occurred_on_utc.tzinfo is UTC


def test_two_domain_events_get_different_ids() -> None:
    first = DomainEvent()
    second = DomainEvent()

    assert first.id != second.id


def test_a_subclass_can_add_its_own_fields_while_keeping_id_and_occurred_on() -> None:
    @dataclass(frozen=True, kw_only=True)
    class UserRegistered(DomainEvent):
        user_id: uuid.UUID

    event = UserRegistered(user_id=uuid.uuid4())

    assert isinstance(event.id, uuid.UUID)
    assert isinstance(event.occurred_on_utc, datetime)
