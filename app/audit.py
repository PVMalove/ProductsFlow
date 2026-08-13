from contextvars import ContextVar

from sqlalchemy import event, insert, inspect
from sqlalchemy.engine import Connection
from sqlalchemy.orm import Mapper

from app.models import AuditAction, User, UserAuditLog

current_actor_id: ContextVar[int | None] = ContextVar("current_actor_id", default=None)


def _resolve_actor(target: User) -> int:
    return current_actor_id.get() or target.id


@event.listens_for(User, "after_insert")
def _on_user_insert(
    _mapper: Mapper[User], connection: Connection, target: User
) -> None:
    connection.execute(
        insert(UserAuditLog).values(
            action=AuditAction.REGISTERED,
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
                action=AuditAction.PASSWORD_CHANGED,
                user_id=target.id,
                actor_user_id=actor,
            )
        )

    if state.attrs.is_active.history.has_changes():
        action: AuditAction | AuditAction = (
            AuditAction.ACTIVATED if target.is_active else AuditAction.DEACTIVATED
        )
        connection.execute(
            insert(UserAuditLog).values(
                action=action,
                user_id=target.id,
                actor_user_id=actor,
            )
        )
