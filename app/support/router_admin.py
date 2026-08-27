from typing import Annotated

from fastapi import APIRouter, Depends, HTTPException, Path, Query, status

from app.security import AdminUser, require_admin
from app.support.models import SenderRole, SupportStatus
from app.support.repository import SupportRepositoryDI
from app.support.schemas import (
    ConversationResponse,
    ConversationWithMessages,
    MessageCreate,
    MessageResponse,
    SupportCounts,
)

router = APIRouter(
    prefix="/admin/support",
    tags=["admin-support"],
    dependencies=[Depends(require_admin)],
)
ConversationId = Annotated[int, Path(gt=0)]


@router.get(
    "/conversations/count",
    response_model=SupportCounts,
)
async def get_conversation_counts(
    repository: SupportRepositoryDI,
) -> SupportCounts:
    return await repository.get_support_counts()


@router.get(
    "/conversations/{conversation_id}",
    response_model=ConversationWithMessages,
)
async def get_conversation(
    conversation_id: ConversationId,
    repository: SupportRepositoryDI,
) -> ConversationWithMessages:
    conversation = await repository.get_conversation_by_id(conversation_id)
    if conversation is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Обращение не найдено",
        )

    messages = await repository.get_thread_messages(conversation_id)
    return ConversationWithMessages(
        **conversation.model_dump(),
        messages=messages,
    )


@router.post(
    "/conversations/{conversation_id}/messages",
    response_model=MessageResponse,
    status_code=status.HTTP_201_CREATED,
)
async def add_admin_message(
    request: MessageCreate,
    conversation_id: ConversationId,
    repository: SupportRepositoryDI,
    current_admin: AdminUser,
) -> MessageResponse:
    conversation = await repository.get_conversation_orm_by_id(conversation_id)
    if conversation is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Обращение не найдено",
        )
    if conversation.status is SupportStatus.CLOSED:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail="Нельзя отправить сообщение в закрытое обращение",
        )

    message = await repository.add_message(
        conversation_id=conversation_id,
        message=request.message,
        sender_user_id=current_admin.id,
        sender_role=SenderRole.ADMIN,
    )
    if message is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Обращение не найдено",
        )
    return message


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
