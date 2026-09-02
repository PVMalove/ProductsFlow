import uuid
from datetime import datetime
from typing import Any

from pydantic import BaseModel, Field, field_validator

from domain.message import TicketMessage
from domain.repositories import PageInfo, TicketPage
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
    page_info: "PageInfoResponse | None" = None

    @classmethod
    def from_domain(
        cls,
        ticket: Ticket,
        page_info: "PageInfoResponse | None" = None,
        messages: list[TicketMessage] | None = None,
    ) -> "TicketResponse":
        source_messages = ticket.messages if messages is None else messages
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
                for message in source_messages
            ],
            page_info=page_info,
        )


class PageInfoResponse(BaseModel):
    next_cursor: str | None
    prev_cursor: str | None
    has_more: bool
    has_prev: bool

    @classmethod
    def from_domain(cls, page_info: PageInfo) -> "PageInfoResponse":
        return cls(
            next_cursor=page_info.next_cursor,
            prev_cursor=page_info.prev_cursor,
            has_more=page_info.has_more,
            has_prev=page_info.has_prev,
        )


class TicketListResponse(BaseModel):
    items: list[TicketResponse]
    page_info: PageInfoResponse

    @classmethod
    def from_domain(cls, page: TicketPage) -> "TicketListResponse":
        return cls(
            items=[TicketResponse.from_domain(ticket) for ticket in page.items],
            page_info=PageInfoResponse.from_domain(page.page_info),
        )
