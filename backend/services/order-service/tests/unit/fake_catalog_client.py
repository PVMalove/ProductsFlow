"""Фейковый CatalogQuotePort для юнит-тестов CheckoutCommandHandler
(issue #372)."""

import uuid

from application.ports import QuoteLine, QuoteResult


class FakeCatalogClient:
    def __init__(
        self,
        *,
        prices_by_product_id: dict[uuid.UUID, int] | None = None,
        unavailable_product_ids: set[uuid.UUID] | None = None,
    ) -> None:
        self._prices = dict(prices_by_product_id or {})
        self._unavailable = set(unavailable_product_ids or set())
        self.calls: list[tuple[uuid.UUID, int, str]] = []

    def set_price(self, product_id: uuid.UUID, unit_price_kopecks: int) -> None:
        self._prices[product_id] = unit_price_kopecks

    def mark_unavailable(self, product_id: uuid.UUID) -> None:
        self._unavailable.add(product_id)

    async def get_quote(
        self, product_id: uuid.UUID, quantity: int, *, bearer_token: str
    ) -> QuoteResult:
        self.calls.append((product_id, quantity, bearer_token))
        if product_id in self._unavailable:
            return QuoteResult.unavailable()
        unit_price_kopecks = self._prices.get(product_id, 1_000)
        return QuoteResult.success(
            QuoteLine(
                product_id=product_id,
                unit_price_kopecks=unit_price_kopecks,
                quantity=quantity,
            )
        )
