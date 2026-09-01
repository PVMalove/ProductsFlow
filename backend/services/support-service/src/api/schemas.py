import uuid
from datetime import datetime
from typing import Any

from pydantic import BaseModel, Field, field_validator

from domain.ticket import Ticket


class TicketCreateRequest(BaseModel):
    subject: str = Field(min_length=1, max_length=200)
    first_message: str = Field(min_length=1, max_length=10_000)

    @field_validator("subject", "first_message", mode="before")
    @classmethod
    def trim_plaintext(cls, value: Any) -> Any:
        return value.strip() if isinstance(value, str) else value


class TicketMessageResponse(BaseModel):
    id: uuid.UUID
    author_id: uuid.UUID
    body: str
    created_at: datetime


class TicketResponse(BaseModel):
    id: uuid.UUID
    author_id: uuid.UUID
    subject: str
    status: str
    messages: list[TicketMessageResponse]

    @classmethod
    def from_domain(cls, ticket: Ticket) -> "TicketResponse":
        return cls(
            id=ticket.id,
            author_id=ticket.author_id,
            subject=ticket.subject,
            status=ticket.status,
            messages=[
                TicketMessageResponse(
                    id=message.id,
                    author_id=message.author_id,
                    body=message.body,
                    created_at=message.created_at,
                )
                for message in ticket.messages
            ],
        )
