"""Общие builders `Order` на заданном шаге Saga для unit-тестов handler'ов и
домена (issue #377): переход шагов собирается здесь один раз, а не копируется
в каждый тестовый файл."""

import uuid

from domain.entities.order import AuthorizationOutcome, Order, OrderLine


def order_awaiting_reservation(
    *,
    user_id: uuid.UUID,
    quantities: tuple[int, ...] = (1,),
    unit_price_kopecks: int = 100,
) -> Order:
    lines = [
        OrderLine(
            id=uuid.uuid4(),
            product_id=uuid.uuid4(),
            quantity=quantity,
            unit_price_kopecks=unit_price_kopecks,
        )
        for quantity in quantities
    ]
    return Order.create(uuid.uuid4(), user_id=user_id, lines=lines)


def order_awaiting_authorization(
    *,
    user_id: uuid.UUID,
    quantities: tuple[int, ...] = (1,),
    unit_price_kopecks: int = 100,
    confirmed_lines: int | None = None,
) -> Order:
    """`confirmed_lines` — сколько первых строк подтвердил резерв (по
    умолчанию все)."""
    order = order_awaiting_reservation(
        user_id=user_id, quantities=quantities, unit_price_kopecks=unit_price_kopecks
    )
    confirmed = (
        order.lines if confirmed_lines is None else order.lines[:confirmed_lines]
    )
    order.apply_reservation_result(
        confirmed_product_ids=frozenset(line.product_id for line in confirmed)
    )
    return order


def order_awaiting_allocation(
    *,
    user_id: uuid.UUID,
    authorization_id: uuid.UUID | None = None,
    quantities: tuple[int, ...] = (1,),
    unit_price_kopecks: int = 100,
    confirmed_lines: int | None = None,
) -> Order:
    order = order_awaiting_authorization(
        user_id=user_id,
        quantities=quantities,
        unit_price_kopecks=unit_price_kopecks,
        confirmed_lines=confirmed_lines,
    )
    order.apply_authorization_result(
        outcome=AuthorizationOutcome.AUTHORIZED,
        authorization_id=authorization_id or uuid.uuid4(),
    )
    return order


def order_awaiting_capture(
    *,
    user_id: uuid.UUID,
    authorization_id: uuid.UUID | None = None,
    quantities: tuple[int, ...] = (1,),
    unit_price_kopecks: int = 100,
    confirmed_lines: int | None = None,
) -> Order:
    order = order_awaiting_allocation(
        user_id=user_id,
        authorization_id=authorization_id,
        quantities=quantities,
        unit_price_kopecks=unit_price_kopecks,
        confirmed_lines=confirmed_lines,
    )
    order.apply_allocation_result()
    return order


def order_compensating(
    *,
    user_id: uuid.UUID,
    outcome: AuthorizationOutcome = AuthorizationOutcome.DECLINED,
    quantities: tuple[int, ...] = (1,),
    unit_price_kopecks: int = 100,
    confirmed_lines: int | None = None,
) -> Order:
    """`FAILED` + `COMPENSATING` после отказа/таймаута авторизации."""
    order = order_awaiting_authorization(
        user_id=user_id,
        quantities=quantities,
        unit_price_kopecks=unit_price_kopecks,
        confirmed_lines=confirmed_lines,
    )
    order.apply_authorization_result(outcome=outcome, authorization_id=uuid.uuid4())
    return order
