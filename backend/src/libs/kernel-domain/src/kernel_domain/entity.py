from kernel_domain.domain_event import DomainEvent


class Entity:
    """Базовый строительный блок агрегата (ADR 0013): накапливает доменные
    события и атомарно отдаёт их вызывающему через `pull_events()` — сама
    публикация (Outbox, ADR 0014) остаётся за пределами этого класса."""

    def __init__(self) -> None:
        self._domain_events: list[DomainEvent] = []

    def add_domain_event(self, event: DomainEvent) -> None:
        self._domain_events.append(event)

    def pull_events(self) -> list[DomainEvent]:
        events = self._domain_events
        self._domain_events = []
        return events
