from kernel_domain.domain_event import DomainEvent


class Entity[TId]:
    """Базовый строительный блок агрегата (ADR 0013): равенство по `id` в
    рамках одного конкретного типа (не по значению полей), плюс накопление
    доменных событий, атомарно отдаваемых вызывающему через `pull_events()`
    — сама публикация (Outbox, ADR 0014) остаётся за пределами этого класса."""

    def __init__(self, id: TId) -> None:
        self.id = id
        self._domain_events: list[DomainEvent] = []

    def add_domain_event(self, event: DomainEvent) -> None:
        self._domain_events.append(event)

    def pull_events(self) -> list[DomainEvent]:
        events = self._domain_events
        self._domain_events = []
        return events

    def __eq__(self, other: object) -> bool:
        if type(other) is not type(self):
            return False
        return self is other or self.id == other.id

    def __hash__(self) -> int:
        return hash((type(self), self.id))
