import uuid
from dataclasses import dataclass
from datetime import datetime


@dataclass
class CartLine:
    """Дочерняя сущность агрегата `Cart` (архитектурный бриф issue #369, D6).
    `id` — собственный **plain** `uuid.UUID`, не VO-обёртка (по прецеденту
    `TicketMessage.id`): line-level эндпоинты адресуют ровно одну строку
    напрямую. `product_id` — сырой id из catalog, не резолвится синхронно в
    этом тикете (ADR 0016:5 — цена фиксируется только на checkout quote).

    Валидация (`quantity <= 0`) и merge-на-дубликате-товара (D4) — забота
    `Cart`, не этой сущности: `Cart` — единственная точка входа для мутаций."""

    id: uuid.UUID
    product_id: uuid.UUID
    quantity: int
    added_at: datetime
