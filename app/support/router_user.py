from fastapi import APIRouter, status

from app.security import CurrentUser
from app.support.repository import SupportRepositoryDI
from app.support.schemas import ConversationCreate, ConversationResponse

router = APIRouter(prefix="/support", tags=["support"])


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
