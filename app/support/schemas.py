from datetime import datetime

from pydantic import BaseModel, ConfigDict, Field

from app.support.models import SenderRole, SupportStatus


class AdminInfo(BaseModel):
    """Минимальное представление админа (избегаем утечки email и хеша пароля)"""

    model_config = ConfigDict(from_attributes=True)

    id: int
    username: str


class SupportCounts(BaseModel):
    """Счётчики для админских бейджей (закрытые тикеты не нужны)"""

    new: int
    in_progress: int


class ConversationCreate(BaseModel):
    """Данные от клиента для создания нового тикета"""

    subject: str = Field(min_length=1, max_length=255)
    # Защита от пустых сообщений и гигантских спам-вставок
    message: str = Field(min_length=3, max_length=4000)


class MessageCreate(BaseModel):
    """Данные от клиента для отправки нового сообщения в существующий тикет"""

    message: str = Field(min_length=3, max_length=4000)


class MessageResponse(BaseModel):
    """Представление одного сообщения"""

    model_config = ConfigDict(from_attributes=True)

    id: int
    sender_role: SenderRole
    sender_user_id: int | None = None
    message: str
    created_at: datetime


class ConversationResponse(BaseModel):
    """Полное представление обращения (метаданные)"""

    model_config = ConfigDict(from_attributes=True)

    id: int
    created_by_user_id: int
    subject: str
    status: SupportStatus
    assignee: AdminInfo | None = None
    first_admin_reply_at: datetime | None = None
    last_message_at: datetime
    last_message_by_role: SenderRole
    created_at: datetime
    updated_at: datetime
    closed_at: datetime | None = None
    user_last_read_at: datetime | None = None


class ConversationWithMessages(ConversationResponse):
    """Обращение вместе с историей переписки"""

    messages: list[MessageResponse]
