"""Сквозной HTTP `POST /api/v1/orders/{order_id}/cancel` через реальный
Postgres + FakeIdentityClient (issue #377, AC1): отмена до capture -> 200,
`CANCELLED` и intents компенсации в `reservation_outbox`; не отменяемый Order
-> 409 без изменений; чужой/неизвестный -> 403/404; без токена -> 401;
identity недоступен -> 503; повтор -> 200 без новой строки outbox."""

import uuid
from datetime import UTC, datetime

import httpx
import pytest
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from domain.entities.order import Order, OrderLine, OrderSagaStep, OrderStatus
from infrastructure.db.entity_configurations.models import (
    OrderSagaTransitionModel,
    ReservationOutboxModel,
)
from infrastructure.db.order_repository import OrderRepository
from tests.integration.fake_identity_client import FakeIdentityClient

pytestmark = pytest.mark.asyncio(loop_scope="session")

TOKEN = "user-token"
HEADERS = {"Authorization": f"Bearer {TOKEN}"}


async def _seed_order(
    db_session: AsyncSession,
    *,
    user_id: uuid.UUID,
    status: OrderStatus = OrderStatus.PENDING,
    saga_step: OrderSagaStep = OrderSagaStep.AWAITING_RESERVATION,
    failure_reason: str | None = None,
    payment_authorization_id: uuid.UUID | None = None,
) -> Order:
    order = Order.reconstitute(
        uuid.uuid4(),
        user_id=user_id,
        status=status,
        saga_step=saga_step,
        lines=[
            OrderLine(
                id=uuid.uuid4(),
                product_id=uuid.uuid4(),
                quantity=2,
                unit_price_kopecks=1_500,
            )
        ],
        failure_reason=failure_reason,
        created_at=datetime.now(UTC),
        payment_authorization_id=payment_authorization_id,
    )
    await OrderRepository(db_session).save(order)
    # Commit (RELEASE SAVEPOINT в `db_session`): отклонённая отмена откатывает
    # сессию, и незафиксированный seed исчез бы вместе с ней.
    await db_session.commit()
    return order


async def _outbox_rows(
    db_session: AsyncSession, order_id: uuid.UUID
) -> list[tuple[str, dict[str, object]]]:
    rows = (
        await db_session.scalars(
            select(ReservationOutboxModel).where(
                ReservationOutboxModel.order_id == order_id
            )
        )
    ).all()
    return sorted((row.command_type, row.payload) for row in rows)


async def _journal(
    db_session: AsyncSession, order_id: uuid.UUID
) -> list[tuple[str, str]]:
    rows = (
        await db_session.scalars(
            select(OrderSagaTransitionModel)
            .where(OrderSagaTransitionModel.order_id == order_id)
            .order_by(OrderSagaTransitionModel.id)
        )
    ).all()
    return [(row.saga_step, row.status) for row in rows]


async def _cancel(
    cart_client: httpx.AsyncClient, order_id: uuid.UUID
) -> httpx.Response:
    return await cart_client.post(f"/api/v1/orders/{order_id}/cancel", headers=HEADERS)


async def test_cancel_awaiting_allocation_voids_and_releases(
    cart_client: httpx.AsyncClient,
    identity_client: FakeIdentityClient,
    db_session: AsyncSession,
) -> None:
    user_id = uuid.uuid4()
    identity_client.register(TOKEN, user_id=user_id)
    authorization_id = uuid.uuid4()
    order = await _seed_order(
        db_session,
        user_id=user_id,
        saga_step=OrderSagaStep.AWAITING_ALLOCATION,
        payment_authorization_id=authorization_id,
    )

    response = await _cancel(cart_client, order.id)

    assert response.status_code == 200
    body = response.json()["data"]
    assert body["id"] == str(order.id)
    assert body["status"] == "cancelled"
    assert body["failure_reason"] == "CANCELLED_BY_CUSTOMER"
    assert "saga_step" not in body
    assert await _outbox_rows(db_session, order.id) == [
        ("inventory.release.v1", {"order_id": str(order.id)}),
        ("payment.void.v1", {"authorization_id": str(authorization_id)}),
    ]
    assert (await _journal(db_session, order.id))[-1] == ("compensating", "cancelled")


async def test_cancel_awaiting_authorization_releases_without_void(
    cart_client: httpx.AsyncClient,
    identity_client: FakeIdentityClient,
    db_session: AsyncSession,
) -> None:
    user_id = uuid.uuid4()
    identity_client.register(TOKEN, user_id=user_id)
    order = await _seed_order(
        db_session, user_id=user_id, saga_step=OrderSagaStep.AWAITING_AUTHORIZATION
    )

    response = await _cancel(cart_client, order.id)

    assert response.status_code == 200
    assert await _outbox_rows(db_session, order.id) == [
        ("inventory.release.v1", {"order_id": str(order.id)})
    ]


async def test_cancel_awaiting_reservation_defers_compensation(
    cart_client: httpx.AsyncClient,
    identity_client: FakeIdentityClient,
    db_session: AsyncSession,
) -> None:
    user_id = uuid.uuid4()
    identity_client.register(TOKEN, user_id=user_id)
    order = await _seed_order(db_session, user_id=user_id)

    response = await _cancel(cart_client, order.id)

    assert response.status_code == 200
    assert response.json()["data"]["status"] == "cancelled"
    assert await _outbox_rows(db_session, order.id) == []
    assert (await _journal(db_session, order.id))[-1] == (
        "awaiting_reservation",
        "cancelled",
    )


@pytest.mark.parametrize(
    ("status", "saga_step", "failure_reason"),
    [
        (OrderStatus.PENDING, OrderSagaStep.AWAITING_CAPTURE, None),
        (OrderStatus.COMPLETED, OrderSagaStep.CAPTURED, None),
        (OrderStatus.FAILED, OrderSagaStep.COMPENSATING, "PAYMENT_DECLINED"),
        (OrderStatus.FAILED, OrderSagaStep.COMPENSATED, "PAYMENT_DECLINED"),
        (OrderStatus.FAILED, OrderSagaStep.RESERVATION_FAILED, "NO_ITEMS_AVAILABLE"),
        (OrderStatus.EXPIRED, OrderSagaStep.COMPENSATED, "RESERVATION_EXPIRED"),
    ],
    ids=[
        "awaiting_capture",
        "captured",
        "failed_compensating",
        "failed_compensated",
        "reservation_failed",
        "expired",
    ],
)
async def test_cancel_of_a_non_cancellable_order_conflicts_without_changes(
    cart_client: httpx.AsyncClient,
    identity_client: FakeIdentityClient,
    db_session: AsyncSession,
    status: OrderStatus,
    saga_step: OrderSagaStep,
    failure_reason: str | None,
) -> None:
    user_id = uuid.uuid4()
    identity_client.register(TOKEN, user_id=user_id)
    order = await _seed_order(
        db_session,
        user_id=user_id,
        status=status,
        saga_step=saga_step,
        failure_reason=failure_reason,
        payment_authorization_id=uuid.uuid4(),
    )
    journal_before = await _journal(db_session, order.id)

    response = await _cancel(cart_client, order.id)

    assert response.status_code == 409
    assert response.json()["error"]["code"] == "order_not_cancellable"
    stored = await OrderRepository(db_session).get_by_id(order.id)
    assert stored is not None
    assert stored.status is status
    assert stored.saga_step is saga_step
    assert stored.failure_reason == failure_reason
    assert await _outbox_rows(db_session, order.id) == []
    assert await _journal(db_session, order.id) == journal_before


async def test_repeated_cancel_returns_200_without_a_new_outbox_row(
    cart_client: httpx.AsyncClient,
    identity_client: FakeIdentityClient,
    db_session: AsyncSession,
) -> None:
    user_id = uuid.uuid4()
    identity_client.register(TOKEN, user_id=user_id)
    order = await _seed_order(
        db_session,
        user_id=user_id,
        saga_step=OrderSagaStep.AWAITING_ALLOCATION,
        payment_authorization_id=uuid.uuid4(),
    )
    first = await _cancel(cart_client, order.id)
    rows_after_first = await _outbox_rows(db_session, order.id)
    journal_after_first = await _journal(db_session, order.id)

    second = await _cancel(cart_client, order.id)

    assert first.status_code == 200
    assert second.status_code == 200
    assert second.json()["data"]["status"] == "cancelled"
    assert await _outbox_rows(db_session, order.id) == rows_after_first
    assert await _journal(db_session, order.id) == journal_after_first


async def test_cancel_of_a_foreign_order_is_denied(
    cart_client: httpx.AsyncClient,
    identity_client: FakeIdentityClient,
    db_session: AsyncSession,
) -> None:
    identity_client.register(TOKEN, user_id=uuid.uuid4())
    order = await _seed_order(db_session, user_id=uuid.uuid4())

    response = await _cancel(cart_client, order.id)

    assert response.status_code == 403
    assert response.json()["error"]["code"] == "order_access_denied"
    stored = await OrderRepository(db_session).get_by_id(order.id)
    assert stored is not None
    assert stored.status is OrderStatus.PENDING


async def test_cancel_of_an_unknown_order_is_not_found(
    cart_client: httpx.AsyncClient, identity_client: FakeIdentityClient
) -> None:
    identity_client.register(TOKEN, user_id=uuid.uuid4())

    response = await _cancel(cart_client, uuid.uuid4())

    assert response.status_code == 404
    assert response.json()["error"]["code"] == "order_not_found"


async def test_cancel_requires_authentication(
    cart_client: httpx.AsyncClient,
) -> None:
    response = await cart_client.post(f"/api/v1/orders/{uuid.uuid4()}/cancel")

    assert response.status_code == 401


async def test_cancel_when_identity_is_unavailable_returns_503(
    cart_client: httpx.AsyncClient,
    identity_client: FakeIdentityClient,
    db_session: AsyncSession,
) -> None:
    user_id = uuid.uuid4()
    identity_client.register(TOKEN, user_id=user_id)
    identity_client.unavailable = True
    order = await _seed_order(db_session, user_id=user_id)

    response = await _cancel(cart_client, order.id)

    assert response.status_code == 503
    stored = await OrderRepository(db_session).get_by_id(order.id)
    assert stored is not None
    assert stored.status is OrderStatus.PENDING


async def test_cancel_by_an_inactive_user_is_denied(
    cart_client: httpx.AsyncClient,
    identity_client: FakeIdentityClient,
    db_session: AsyncSession,
) -> None:
    user_id = uuid.uuid4()
    identity_client.register(TOKEN, user_id=user_id, is_active=False)
    order = await _seed_order(db_session, user_id=user_id)

    response = await _cancel(cart_client, order.id)

    assert response.status_code == 403
    stored = await OrderRepository(db_session).get_by_id(order.id)
    assert stored is not None
    assert stored.status is OrderStatus.PENDING
