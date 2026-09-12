# ruff: noqa: E501
import uuid
from datetime import datetime

from kernel_platform.outbox.drain import drain_events_to_outbox
from sqlalchemy import select
from sqlalchemy.dialects.postgresql import insert as pg_insert
from sqlalchemy.ext.asyncio import AsyncSession

from domain.entities.reservation import (
    Reservation,
    ReservationLine,
    ReservationLineStatus,
)
from domain.repositories import ReservationRepository as ReservationRepositoryPort
from domain.reservation_status import ReservationStatus
from infrastructure.db.entity_configurations.models import (
    ReservationLineModel,
    ReservationModel,
)


class ReservationRepository:
    """CRUD для `Reservation`/`ReservationLine` (issue #370). Мутирующие
    методы дренируют доменные события в outbox в точке мутации; фиксация
    транзакции остаётся за вызывающим (message-driven handler — issue #370
    D8, находка 3 — никогда не коммитит самостоятельно)."""

    def __init__(self, session: AsyncSession) -> None:
        self.session = session

    async def get_by_order_id(self, order_id: uuid.UUID) -> Reservation | None:
        row = await self.session.get(ReservationModel, order_id)
        if row is None:
            return None
        return await self._to_domain(row)

    async def try_create(self, reservation: Reservation) -> bool:
        # D3: natural PK (order_id) идемпотентность — тот же идиом, что
        # `InventoryRepository.create_zero()` (issue #367).
        inserted_id = await self.session.scalar(
            pg_insert(ReservationModel)
            .values(
                order_id=reservation.id,
                status=reservation.status.value,
                expires_at=reservation.expires_at,
                created_at=reservation.created_at,
            )
            .on_conflict_do_nothing(index_elements=[ReservationModel.order_id])
            .returning(ReservationModel.order_id)
        )
        if inserted_id is None:
            return False

        for line in reservation.lines:
            self.session.add(
                ReservationLineModel(
                    id=line.id,
                    reservation_id=reservation.id,
                    product_id=line.product_id,
                    quantity=line.quantity,
                    status=line.status.value,
                )
            )
        await drain_events_to_outbox(self.session, reservation)
        return True

    async def claim_expired(self, *, now: datetime, limit: int) -> list[Reservation]:
        # D6: `SKIP LOCKED` — на будущее горизонтальное масштабирование
        # inventory-worker; строки уже заблокированы `FOR UPDATE` в текущей
        # транзакции вызывающего (sweep обрабатывает их по одной).
        rows = (
            await self.session.scalars(
                select(ReservationModel)
                .where(
                    ReservationModel.status == ReservationStatus.ACTIVE.value,
                    ReservationModel.expires_at <= now,
                )
                .order_by(ReservationModel.expires_at.asc())
                .limit(limit)
                .with_for_update(skip_locked=True)
            )
        ).all()
        return [await self._to_domain(row) for row in rows]

    async def save(self, reservation: Reservation) -> None:
        row = await self.session.get(ReservationModel, reservation.id)
        assert row is not None, "save() expects an already-persisted reservation"
        row.status = reservation.status.value
        await drain_events_to_outbox(self.session, reservation)

    async def _to_domain(self, row: ReservationModel) -> Reservation:
        line_rows = (
            await self.session.scalars(
                select(ReservationLineModel).where(
                    ReservationLineModel.reservation_id == row.order_id
                )
            )
        ).all()
        lines = [
            ReservationLine(
                id=line_row.id,
                product_id=line_row.product_id,
                quantity=line_row.quantity,
                status=ReservationLineStatus(line_row.status),
            )
            for line_row in line_rows
        ]
        return Reservation.reconstitute(
            row.order_id,
            status=ReservationStatus(row.status),
            lines=lines,
            expires_at=row.expires_at,
            created_at=row.created_at,
        )


# Статическая структурная проверка: mypy убеждается, что конкретная
# реализация удовлетворяет каждую операцию, требуемую доменным контрактом
# репозитория.
_reservation_repository_implementation: type[ReservationRepositoryPort] = (
    ReservationRepository
)
