# ruff: noqa: E501
"""Команда и handler оформления заказа (issue #372, D5) — одна локальная
транзакция: quote -> Idempotency-Key check/replay -> Pending Order ->
selection freeze -> reservation_outbox intent, all-or-nothing."""

import logging
import uuid
from dataclasses import dataclass
from datetime import UTC, datetime

from kernel_domain.result import Result
from kernel_platform.security import Actor

from application.errors import CatalogUnavailableError
from application.ports import CatalogQuotePort
from contracts.order import OrderView
from domain.checkout_fingerprint import compute_fingerprint
from domain.entities.idempotency_key import IdempotencyKeyRecord
from domain.entities.order import Order, OrderLine
from domain.errors import OrderErrors
from domain.unit_of_work import CheckoutUnitOfWork

logger = logging.getLogger(__name__)


@dataclass(frozen=True)
class CheckoutCommand:
    """DTO для оформления заказа из текущего содержимого Cart вызывающего
    (D2 — checkout не принимает список товаров, только Idempotency-Key).
    `bearer_token` форвардится в Catalog Quote от имени покупателя (D9)."""

    actor: Actor
    idempotency_key: str
    bearer_token: str


class CheckoutCommandHandler:
    """
    Business Logic Summary

    Context & Purpose: Оформление заказа из текущей серверной корзины вызывающего — авторитетный quote, идемпотентность, частичный async reservation round-trip.
    Validations: Корзина не пуста (иначе Result-ошибка); Idempotency-Key с изменившимся fingerprint конфликтует (Result-ошибка); недоступный/отказавший Catalog поднимает CatalogUnavailableError — ничего не персистится (D1).
    Side Effects: Идентичный повтор (user_id, Idempotency-Key) возвращает существующий Order без повторного quote (D2). Иначе: создаёт Order, блокирует строки корзины (Cart.lock_for_checkout), пишет Idempotency-Key запись и reservation_outbox intent — всё в одной транзакции (D5).
    """

    def __init__(self, uow: CheckoutUnitOfWork, catalog: CatalogQuotePort) -> None:
        self._uow = uow
        self._catalog = catalog

    async def execute(self, command: CheckoutCommand) -> Result[OrderView]:
        async with self._uow:
            cart = await self._uow.carts.get_locked_for_user(command.actor.id)
            if cart is None or not cart.lines:
                logger.warning(
                    "Checkout отклонён: user_id=%s корзина пуста", command.actor.id
                )
                return Result[OrderView].fail(OrderErrors.empty_cart())

            fingerprint = compute_fingerprint(cart.lines)
            existing = await self._uow.idempotency_keys.get(
                command.actor.id, command.idempotency_key
            )
            if existing is not None:
                if existing.request_fingerprint != fingerprint:
                    logger.warning(
                        "Checkout отклонён: Idempotency-Key %s уже использован "
                        "с другим содержимым корзины (user_id=%s)",
                        command.idempotency_key,
                        command.actor.id,
                    )
                    return Result[OrderView].fail(OrderErrors.idempotency_key_conflict())

                order = await self._uow.orders.get_by_id(existing.order_id)
                assert order is not None, (
                    "idempotency_keys.order_id ссылается на существующий Order"
                )
                logger.info(
                    "Checkout: реплей Idempotency-Key %s -> order_id=%s",
                    command.idempotency_key,
                    order.id,
                )
                return Result[OrderView].ok(OrderView.from_domain(order))

            quoted_lines: list[OrderLine] = []
            for line in cart.lines:
                quote = await self._catalog.get_quote(
                    line.product_id, line.quantity, bearer_token=command.bearer_token
                )
                if not quote.ok or quote.line is None:
                    logger.warning(
                        "Checkout отклонён: catalog quote недоступен "
                        "product_id=%s user_id=%s",
                        line.product_id,
                        command.actor.id,
                    )
                    raise CatalogUnavailableError
                quoted_lines.append(
                    OrderLine(
                        id=uuid.uuid4(),
                        product_id=line.product_id,
                        quantity=line.quantity,
                        unit_price_kopecks=quote.line.unit_price_kopecks,
                    )
                )

            order = Order.create(
                uuid.uuid4(), user_id=command.actor.id, lines=quoted_lines
            )
            cart.lock_for_checkout(order_id=order.id)

            await self._uow.orders.save(order)
            await self._uow.idempotency_keys.save(
                IdempotencyKeyRecord(
                    user_id=command.actor.id,
                    key=command.idempotency_key,
                    request_fingerprint=fingerprint,
                    order_id=order.id,
                    created_at=datetime.now(UTC),
                )
            )
            await self._uow.carts.save(cart)
            await self._uow.reservation_outbox.enqueue(
                order_id=order.id, lines=quoted_lines
            )
            await self._uow.commit()

        logger.info(
            "Checkout создал order_id=%s user_id=%s lines=%d",
            order.id,
            command.actor.id,
            len(order.lines),
        )
        return Result[OrderView].ok(OrderView.from_domain(order))
