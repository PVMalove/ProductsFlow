# ruff: noqa: E501
"""Create-ticket command and handler."""

import uuid
from dataclasses import dataclass

from application.ports import TicketCommandPort
from domain.ticket import Ticket


@dataclass(frozen=True)
class CreateTicketCommand:
    """DTO для создания нового тикета."""

    """
    DTO команды для создания нового тикета поддержки.
    
    Attributes:
        author_id (uuid.UUID): Идентификатор автора (пользователя), создающего тикет.
        subject (str): Тема тикета.
        first_message (str): Текст первого сообщения в тикете.
    """
    author_id: uuid.UUID
    subject: str
    first_message: str


class CreateTicketCommandHandler:
    """
    Business Logic Summary

    Context & Purpose: Создание нового обращения в службу поддержки.
    Validations: Валидация длины темы и наличия первоначального сообщения в Ticket.create.
    Side Effects: Создается новая сущность Ticket и ее начальное сообщение.
    """

    """
    Business Logic Summary
    
    Context & Purpose: Создает новый тикет поддержки в системе.
    Validations: Специфические валидации бизнес-логики могут происходить внутри метода Ticket.create.
    Side Effects: Создает новую сущность тикета в памяти и сохраняет ее в базу данных через TicketCommandPort.
    """

    def __init__(self, repository: TicketCommandPort) -> None:
        self._repository = repository

    async def execute(self, command: CreateTicketCommand) -> Ticket:
        """
        Создает тикет и сохраняет его в репозитории.

        @param command: Объект CreateTicketCommand с данными для создания.
        @return: Ticket — созданная сущность тикета.
        @raises: Может выбрасывать исключения валидации домена (зависит от Ticket.create).
        """
        ticket = Ticket.create(
            author_id=command.author_id,
            subject=command.subject,
            first_message=command.first_message,
        )
        return await self._repository.create(ticket)
