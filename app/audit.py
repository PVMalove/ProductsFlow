from sqlalchemy.ext.asyncio import AsyncSession

from app.models import AuditAction
from app.repository import AuditLogRepository


async def record(
    session: AsyncSession,
    action: AuditAction,
    user_id: int,
    actor_user_id: int,
    description: str = "",
) -> None:
    await AuditLogRepository(session).add_audit_log(
        action=action,
        user_id=user_id,
        actor_user_id=actor_user_id,
        description=description,
    )
    await session.commit()
