from fastapi import APIRouter, Query, status

from app.security import CurrentUser
from app.support.repository import SupportRepositoryDI
from app.support.schemas import ConversationCreate, ConversationResponse

router = APIRouter(prefix="/support", tags=["support"])


@router.get(
    "/",
    response_model=list[ConversationResponse],
)
async def get_user_conversations(
    repository: SupportRepositoryDI,
    current_user: CurrentUser,
    page_index: int = Query(default=1, ge=1),
    page_size: int = Query(default=10, ge=1),
) -> list[ConversationResponse]:
    return await repository.get_user_conversations(
        user_id=current_user.id,
        limit=page_size,
        offset=(page_index - 1) * page_size,
    )


@router.post(
    "/",
    response_model=ConversationResponse,
    status_code=status.HTTP_201_CREATED,
)
async def create_conversation(
    request: ConversationCreate,
    repository: SupportRepositoryDI,
    current_user: CurrentUser,
) -> ConversationResponse:
    return await repository.create_conversation(
        user_id=current_user.id,
        subject=request.subject,
        message=request.message,
    )
