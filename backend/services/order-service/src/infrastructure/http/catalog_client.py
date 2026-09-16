# ruff: noqa: E501
"""HTTP-клиент к авторитетному Catalog Checkout Quote (issue #372, D9) —
мирует `IdentityClient`'s форму (модульный `httpx.AsyncClient`, один
таймаут/retry конфигурацией самого клиента), не код: Quote — не auth.
Форвардит вызывающего собственный bearer-токен (finding 14) — Quote всегда
запрашивается от имени покупателя, не service-identity."""

import uuid

import httpx

from application.ports import QuoteLine, QuoteResult

DEFAULT_QUOTE_PATH_TEMPLATE = "/api/v1/products/{product_id}/quote"


class CatalogClient:
    def __init__(self, http_client: httpx.AsyncClient) -> None:
        self._http_client = http_client

    async def get_quote(
        self, product_id: uuid.UUID, quantity: int, *, bearer_token: str
    ) -> QuoteResult:
        """Единая классификация отказа (D9/Scope clarification #2): сетевая
        ошибка, timeout, 5xx (Catalog недоступен) и 4xx (товар
        удалён/скрыт/деактивирован) — все схлопываются в один
        `QuoteResult.unavailable()`, не различаемый на этом уровне."""
        try:
            response = await self._http_client.get(
                DEFAULT_QUOTE_PATH_TEMPLATE.format(product_id=product_id),
                params={"quantity": quantity},
                headers={"Authorization": f"Bearer {bearer_token}"},
            )
            response.raise_for_status()
        except httpx.HTTPError:
            return QuoteResult.unavailable()

        body = response.json()
        data = body.get("data", body)
        return QuoteResult.success(
            QuoteLine(
                product_id=uuid.UUID(str(data["product_id"])),
                unit_price_kopecks=int(data["unit_price_kopecks"]),
                quantity=int(data["quantity"]),
            )
        )
