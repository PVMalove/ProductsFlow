# ruff: noqa: E501
"""Framework-independent порт синхронного Catalog Quote (issue #372, D9) —
application-слой зависит только от этого `Protocol`, не от `httpx`/конкретного
HTTP-клиента (hexagonal layering, CLAUDE.md)."""

import uuid
from dataclasses import dataclass
from typing import Protocol


@dataclass(frozen=True)
class QuoteLine:
    """Авторитетная цена одной строки, полученная от Catalog (ADR 0016:5,9,17
    — коммерческий снимок, не пересчитывается позже)."""

    product_id: uuid.UUID
    unit_price_kopecks: int
    quantity: int


@dataclass(frozen=True)
class QuoteResult:
    """Единый исход `CatalogClient.get_quote` — не различает причину отказа
    (timeout/5xx/4xx business-отказ, D9/Scope clarification #2): любая
    ошибка блокирует весь checkout одинаково."""

    ok: bool
    line: QuoteLine | None = None

    @classmethod
    def success(cls, line: QuoteLine) -> "QuoteResult":
        return cls(ok=True, line=line)

    @classmethod
    def unavailable(cls) -> "QuoteResult":
        return cls(ok=False, line=None)


class CatalogQuotePort(Protocol):
    async def get_quote(
        self, product_id: uuid.UUID, quantity: int, *, bearer_token: str
    ) -> QuoteResult: ...
