from typing import Annotated

from fastapi import APIRouter, HTTPException, Path, Query, status

from app.models import User as UserORM
from app.security import CurrentUser
from app.support.models import Conversation as ConversationORM
from app.support.models import SenderRole, SupportStatus
from app.support.repository import SupportRepositoryDI
from app.support.schemas import (
    ConversationCreate,
    ConversationResponse,
    ConversationWithMessages,
    MessageCreate,
    MessageResponse,
)

router = APIRouter(prefix="/support", tags=["support"])
ConversationId = Annotated[int, Path(gt=0)]


def _ensure_owner(conversation: ConversationORM, user: UserORM) -> None:
    if conversation.created_by_user_id != user.id:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Обращение не найдено",
        )


@router.get(
    "/{conversation_id}",
    response_model=ConversationWithMessages,
)
async def get_conversation(
    conversation_id: ConversationId,
    repository: SupportRepositoryDI,
    current_user: CurrentUser,
) -> ConversationWithMessages:
    conversation: ConversationORM | None = await repository.get_conversation_orm_by_id(
        conversation_id
    )
    if conversation is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Обращение не найдено",
        )
    _ensure_owner(conversation, current_user)

    response: ConversationResponse = ConversationResponse.model_validate(conversation)
    messages: list[MessageResponse] = await repository.get_thread_messages(
        conversation_id
    )
    return ConversationWithMessages(
        **response.model_dump(),
        messages=messages,
    )


@router.post(
    "/conversations/{conversation_id}/messages",
    response_model=MessageResponse,
    status_code=status.HTTP_201_CREATED,
)
async def add_message(
    request: MessageCreate,
    conversation_id: ConversationId,
    repository: SupportRepositoryDI,
    current_user: CurrentUser,
) -> MessageResponse:
    conversation: ConversationORM | None = await repository.get_conversation_orm_by_id(
        conversation_id
    )
    if conversation is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Обращение не найдено",
        )
    _ensure_owner(conversation, current_user)
    if conversation.status is SupportStatus.CLOSED:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail="Нельзя отправить сообщение в закрытое обращение",
        )

    message: MessageResponse | None = await repository.add_message(
        conversation_id=conversation_id,
        message=request.message,
        sender_user_id=current_user.id,
        sender_role=SenderRole.USER,
    )
    if message is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Обращение не найдено",
        )
    return message


@router.post(
    "/conversations/{conversation_id}/read",
    response_model=ConversationResponse,
)
async def mark_conversation_as_read(
    conversation_id: ConversationId,
    repository: SupportRepositoryDI,
    current_user: CurrentUser,
) -> ConversationResponse:
    conversation: ConversationORM | None = await repository.get_conversation_orm_by_id(
        conversation_id
    )
    if conversation is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Обращение не найдено",
        )
    _ensure_owner(conversation, current_user)

    updated_conversation: ConversationResponse | None = await repository.mark_as_read(
        conversation_id, is_admin=False
    )
    if updated_conversation is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Обращение не найдено",
        )
    return updated_conversation


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
