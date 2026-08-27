from datetime import datetime, timezone
from typing import Annotated

from fastapi import Depends
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import joinedload

from app.db import Session
from app.support.models import (
    Conversation,
    ConversationMessage,
    SenderRole,
    SupportStatus,
)
from app.support.schemas import (
    ConversationResponse,
    MessageResponse,
    SupportCounts,
)


class SupportRepository:
    def __init__(self, session: AsyncSession) -> None:
        self.session = session

    async def get_conversation_by_id(
        self, conversation_id: int
    ) -> ConversationResponse | None:
        """Загружает обращение вместе с назначенным администратором."""
        conversation = await self.get_conversation_orm_by_id(conversation_id)
        return (
            ConversationResponse.model_validate(conversation) if conversation else None
        )

    async def get_conversation_orm_by_id(
        self, conversation_id: int
    ) -> Conversation | None:
        stmt = (
            select(Conversation)
            .options(joinedload(Conversation.assignee))
            .where(Conversation.id == conversation_id)
        )
        return await self.session.scalar(stmt)

    async def get_user_conversations(
        self, user_id: int, limit: int, offset: int
    ) -> list[ConversationResponse]:
        """Возвращает обращения пользователя, начиная с offset."""
        stmt = (
            select(Conversation)
            .options(joinedload(Conversation.assignee))
            .where(Conversation.created_by_user_id == user_id)
            .order_by(Conversation.last_message_at.desc(), Conversation.id.desc())
            .limit(limit)
            .offset(offset)
        )
        result = await self.session.scalars(stmt)
        return [ConversationResponse.model_validate(row) for row in result.all()]

    async def create_conversation(
        self, user_id: int, subject: str, message: str
    ) -> ConversationResponse:
        """Создаёт обращение вместе с его первым сообщением."""
        conversation = Conversation(
            created_by_user_id=user_id,
            subject=subject,
            status=SupportStatus.NEW,
            last_message_by_role=SenderRole.USER,
        )
        conversation.messages.append(
            ConversationMessage(
                sender_user_id=user_id,
                sender_role=SenderRole.USER,
                message=message,
            )
        )
        self.session.add(conversation)
        await self.session.commit()
        await self.session.refresh(conversation)
        return ConversationResponse.model_validate(conversation)

    async def add_message(
        self,
        conversation_id: int,
        message: str,
        sender_user_id: int | None,
        sender_role: SenderRole,
    ) -> MessageResponse | None:
        """Добавляет сообщение и обновляет время/роль последней активности."""
        conversation = await self.session.get(Conversation, conversation_id)
        if conversation is None:
            return None

        new_message = ConversationMessage(
            conversation_id=conversation_id,
            sender_user_id=sender_user_id,
            sender_role=sender_role,
            message=message,
        )
        self.session.add(new_message)
        conversation.last_message_at = func.now()
        conversation.last_message_by_role = sender_role
        if (
            sender_role is SenderRole.ADMIN
            and conversation.first_admin_reply_at is None
        ):
            conversation.first_admin_reply_at = func.now()

        await self.session.commit()
        await self.session.refresh(new_message)
        return MessageResponse.model_validate(new_message)

    async def close_conversation(
        self, conversation_id: int
    ) -> ConversationResponse | None:
        """Закрывает обращение и сохраняет время закрытия."""
        conversation = await self.session.get(Conversation, conversation_id)
        if conversation is None:
            return None
        if conversation.status is SupportStatus.CLOSED:
            return await self.get_conversation_by_id(conversation_id)

        conversation.status = SupportStatus.CLOSED
        conversation.closed_at = datetime.now(timezone.utc)
        await self.session.commit()
        await self.session.refresh(conversation)
        return ConversationResponse.model_validate(conversation)

    async def mark_as_read(
        self, conversation_id: int, is_admin: bool
    ) -> ConversationResponse | None:
        """Помечает обращение прочитанным пользователем или администратором."""
        conversation = await self.session.get(Conversation, conversation_id)
        if conversation is None:
            return None

        read_at = datetime.now(timezone.utc)
        if is_admin:
            conversation.admin_last_read_at = read_at
        else:
            conversation.user_last_read_at = read_at
        await self.session.commit()
        await self.session.refresh(conversation)
        return ConversationResponse.model_validate(conversation)

    async def get_support_counts(self) -> SupportCounts:
        """Возвращает количество новых и открытых обращений."""
        result = await self.session.execute(
            select(
                func.count()
                .filter(Conversation.status == SupportStatus.NEW)
                .label("new"),
                func.count()
                .filter(Conversation.status == SupportStatus.IN_PROGRESS)
                .label("in_progress"),
            )
        )
        counts = result.one()
        return SupportCounts(new=counts.new, in_progress=counts.in_progress)

    async def get_admin_conversations(
        self,
        limit: int,
        offset: int,
        status: SupportStatus | None = None,
    ) -> list[ConversationResponse]:
        """Возвращает обращения для админского списка."""
        stmt = select(Conversation).options(joinedload(Conversation.assignee))
        if status is not None:
            stmt = stmt.where(Conversation.status == status)
        stmt = (
            stmt.order_by(Conversation.last_message_at.desc(), Conversation.id.desc())
            .options(joinedload(Conversation.assignee))
            .limit(limit)
            .offset(offset)
        )
        result = await self.session.scalars(stmt)
        return [ConversationResponse.model_validate(row) for row in result.all()]

    async def get_thread_messages(
        self, conversation_id: int, limit: int = 200
    ) -> list[MessageResponse]:
        """Возвращает сообщения треда в хронологическом порядке."""
        stmt = (
            select(ConversationMessage)
            .where(ConversationMessage.conversation_id == conversation_id)
            .order_by(
                ConversationMessage.created_at.asc(), ConversationMessage.id.asc()
            )
            .limit(limit)
        )
        result = await self.session.scalars(stmt)
        return [MessageResponse.model_validate(row) for row in result.all()]


def get_support_repository(session: Session) -> SupportRepository:
    return SupportRepository(session)


SupportRepositoryDI = Annotated[SupportRepository, Depends(get_support_repository)]
