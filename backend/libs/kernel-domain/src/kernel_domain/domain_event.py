# ruff: noqa: E501
import uuid
from dataclasses import dataclass, field
from datetime import UTC, datetime


@dataclass(frozen=True, kw_only=True)
class DomainEvent:
    """Базовый контракт доменного события — без зависимости от
    какого-либо message-фреймворка или брокера. `id` принадлежит событию,
    не агрегату. Подклассы добавляют свои поля через тот же `kw_only=True`."""

    id: uuid.UUID = field(default_factory=uuid.uuid4)
    occurred_on_utc: datetime = field(default_factory=lambda: datetime.now(UTC))
