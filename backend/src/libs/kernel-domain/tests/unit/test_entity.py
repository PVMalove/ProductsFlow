from kernel_domain.domain_event import DomainEvent
from kernel_domain.entity import Entity


def test_a_fresh_entity_has_no_pending_events() -> None:
    entity = Entity()

    assert entity.pull_events() == []


def test_added_events_are_returned_by_pull_events_in_the_order_added() -> None:
    entity = Entity()
    first = DomainEvent()
    second = DomainEvent()

    entity.add_domain_event(first)
    entity.add_domain_event(second)

    assert entity.pull_events() == [first, second]


def test_pull_events_clears_the_store_so_a_second_call_returns_nothing() -> None:
    entity = Entity()
    entity.add_domain_event(DomainEvent())

    entity.pull_events()

    assert entity.pull_events() == []


def test_events_added_after_a_pull_are_returned_by_the_next_pull() -> None:
    entity = Entity()
    entity.add_domain_event(DomainEvent())
    entity.pull_events()

    new_event = DomainEvent()
    entity.add_domain_event(new_event)

    assert entity.pull_events() == [new_event]
