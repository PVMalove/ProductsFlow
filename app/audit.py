from contextvars import ContextVar

from sqlalchemy import event, insert, inspect
from sqlalchemy.engine import Connection
from sqlalchemy.orm import Mapper

from app.models import (
    Product,
    ProductAuditAction,
    ProductAuditLog,
    User,
    UserAuditAction,
    UserAuditLog,
)

current_actor_id: ContextVar[int | None] = ContextVar("current_actor_id", default=None)


def _resolve_actor(target: User) -> int:
    return current_actor_id.get() or target.id


def _resolve_product_actor(target: Product) -> int:
    return current_actor_id.get() or target.user_id


@event.listens_for(User, "after_insert")
def _on_user_insert(
    _mapper: Mapper[User], connection: Connection, target: User
) -> None:
    connection.execute(
        insert(UserAuditLog).values(
            action=UserAuditAction.REGISTERED,
            user_id=target.id,
            actor_user_id=_resolve_actor(target),
        )
    )


@event.listens_for(User, "before_update")
def _on_user_update(
    _mapper: Mapper[User], connection: Connection, target: User
) -> None:
    state = inspect(target)
    actor = _resolve_actor(target)

    if state.attrs.password_hash.history.has_changes():
        connection.execute(
            insert(UserAuditLog).values(
                action=UserAuditAction.PASSWORD_CHANGED,
                user_id=target.id,
                actor_user_id=actor,
            )
        )

    if state.attrs.is_active.history.has_changes():
        action: UserAuditAction | UserAuditAction = (
            UserAuditAction.ACTIVATED
            if target.is_active
            else UserAuditAction.DEACTIVATED
        )
        connection.execute(
            insert(UserAuditLog).values(
                action=action,
                user_id=target.id,
                actor_user_id=actor,
            )
        )


@event.listens_for(Product, "after_insert")
def _on_product_insert(
    _mapper: Mapper[Product], connection: Connection, target: Product
) -> None:
    connection.execute(
        insert(ProductAuditLog).values(
            action=ProductAuditAction.CREATED,
            product_id=target.id,
            actor_user_id=_resolve_product_actor(target),
            description=(
                f'Создан продукт "{target.name}" '
                f"(категория: {target.category}, цена: {target.price})"
            ),
        )
    )


@event.listens_for(Product, "before_update")
def _on_product_update(
    _mapper: Mapper[Product], connection: Connection, target: Product
) -> None:
    state = inspect(target)
    changes: list[str] = []

    for attr in ("name", "category", "price", "description"):
        history = state.attrs[attr].history
        if not history.has_changes():
            continue
        old_value = history.deleted[0] if history.deleted else None
        changes.append(f"{attr}: {old_value!r} -> {getattr(target, attr)!r}")

    if not changes:
        return

    connection.execute(
        insert(ProductAuditLog).values(
            action=ProductAuditAction.UPDATED,
            product_id=target.id,
            actor_user_id=_resolve_product_actor(target),
            description=f'Изменён продукт "{target.name}": ' + "; ".join(changes),
        )
    )


@event.listens_for(Product, "after_delete")
def _on_product_delete(
    _mapper: Mapper[Product], connection: Connection, target: Product
) -> None:
    connection.execute(
        insert(ProductAuditLog).values(
            action=ProductAuditAction.DELETED,
            product_id=target.id,
            actor_user_id=_resolve_product_actor(target),
            description=(
                f'Удалён продукт "{target.name}" (категория: {target.category})'
            ),
        )
    )
