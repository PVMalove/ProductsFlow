from fastapi import APIRouter, Depends, Query

from app.security import require_admin
from app.support.models import SupportStatus
from app.support.repository import SupportRepositoryDI
from app.support.schemas import ConversationResponse, SupportCounts

router = APIRouter(
    prefix="/admin/support",
    tags=["admin-support"],
    dependencies=[Depends(require_admin)],
)


@router.get(
    "/conversations/count",
    response_model=SupportCounts,
)
async def get_conversation_counts(
    repository: SupportRepositoryDI,
) -> SupportCounts:
    return await repository.get_support_counts()


@router.get(
    "/conversations",
    response_model=list[ConversationResponse],
)
async def get_list_all_conversations(
    repository: SupportRepositoryDI,
    page_index: int = Query(default=1, ge=1),
    page_size: int = Query(default=10, ge=1),
    status: SupportStatus | None = Query(default=None),
) -> list[ConversationResponse]:
    return await repository.get_admin_conversations(
        limit=page_size,
        offset=(page_index - 1) * page_size,
        status=status,
    )
