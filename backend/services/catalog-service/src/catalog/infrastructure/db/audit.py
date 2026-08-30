import enum
from datetime import datetime

from kernel_platform.outbox.models import Base
from observability.context import actor_id_var
from sqlalchemy import BigInteger, Identity, Text, event, func, insert, inspect
from sqlalchemy.engine import Connection
from sqlalchemy.orm import Mapped, Mapper, mapped_column

from catalog.infrastructure.db.models import ProductModel


class ProductAuditAction(enum.StrEnum):
    CREATED = "created"
    UPDATED = "updated"
    DELETED = "deleted"
    ACTIVATED = "activated"
    DEACTIVATED = "deactivated"


class ProductAuditLog(Base):
    """Audit-лог мутаций Товара (ADR 0004, issue #148). `product_id` —
    намеренно без FK: audit-строка должна пережить удаление Товара
    (CONTEXT.md «Существование продукта»), как и в монолите."""

    __tablename__ = "product_audit_log"

    id: Mapped[int] = mapped_column(BigInteger, Identity(), primary_key=True)
    product_id: Mapped[int] = mapped_column(BigInteger)
    # `observability.context.actor_id_var` типизирован `int | None` (унаследовано
    # от монолитного int-PK User) — Владелец Товара (`ProductModel.user_id`) уже
    # GUID (identity `UserId`), поэтому монолитный фолбэк «нет Actor'а из
    # контекста -> Actor = Владелец» здесь неприменим по типам: колонка
    # осталась nullable, строка без Actor'а пишется без него, а не с чужим
    # типом данных.
    actor_user_id: Mapped[int | None] = mapped_column(BigInteger, nullable=True)
    action: Mapped[ProductAuditAction] = mapped_column(Text)
    description: Mapped[str] = mapped_column(Text, default="", server_default="")
    created_at: Mapped[datetime] = mapped_column(server_default=func.now())


@event.listens_for(ProductModel, "after_insert")
def _on_product_insert(
    _mapper: Mapper[ProductModel], connection: Connection, target: ProductModel
) -> None:
    connection.execute(
        insert(ProductAuditLog).values(
            action=ProductAuditAction.CREATED,
            product_id=target.id,
            actor_user_id=actor_id_var.get(),
            description=(
                f'Создан товар "{target.name}" '
                f"(категория: {target.category}, цена: {target.price})"
            ),
        )
    )


@event.listens_for(ProductModel, "before_update")
def _on_product_update(
    _mapper: Mapper[ProductModel], connection: Connection, target: ProductModel
) -> None:
    state = inspect(target)
    actor = actor_id_var.get()
    changes: list[str] = []

    for attr in ("name", "category", "price", "description"):
        history = state.attrs[attr].history
        if not history.has_changes():
            continue
        old_value = history.deleted[0] if history.deleted else None
        changes.append(f"{attr}: {old_value!r} -> {getattr(target, attr)!r}")

    if changes:
        connection.execute(
            insert(ProductAuditLog).values(
                action=ProductAuditAction.UPDATED,
                product_id=target.id,
                actor_user_id=actor,
                description=f'Изменён товар "{target.name}": ' + "; ".join(changes),
            )
        )

    if state.attrs.is_active.history.has_changes():
        action = (
            ProductAuditAction.ACTIVATED
            if target.is_active
            else ProductAuditAction.DEACTIVATED
        )
        connection.execute(
            insert(ProductAuditLog).values(
                action=action,
                product_id=target.id,
                actor_user_id=actor,
                description=(
                    f'Товар "{target.name}" активирован'
                    if target.is_active
                    else f'Товар "{target.name}" деактивирован'
                ),
            )
        )


@event.listens_for(ProductModel, "before_delete")
def _on_product_delete(
    _mapper: Mapper[ProductModel], connection: Connection, target: ProductModel
) -> None:
    connection.execute(
        insert(ProductAuditLog).values(
            action=ProductAuditAction.DELETED,
            product_id=target.id,
            actor_user_id=actor_id_var.get(),
            description=(
                f'Удалён товар "{target.name}" (категория: {target.category})'
            ),
        )
    )
