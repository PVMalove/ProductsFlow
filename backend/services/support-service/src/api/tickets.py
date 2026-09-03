import uuid
from typing import Annotated

from fastapi import APIRouter, Depends, status
from kernel_domain.result import Result
from kernel_platform.http.envelope import ApiResponse
from kernel_platform.http.errors import ApiError, status_code_for_error_type
from kernel_platform.http.match import match_created, match_result

from api.dependencies import (
    AddTicketMessageDI,
    ChangeTicketStatusDI,
    CreateTicketDI,
    DeleteTicketMessageDI,
    EditTicketMessageDI,
    GetTicketDetailDI,
    ListAdminTicketsDI,
    ListTicketsDI,
)
from api.schemas import (
    AdminTicketListRequest,
    TicketCreateRequest,
    TicketDetailRequest,
    TicketListRequest,
    TicketMessageCreateRequest,
    TicketMessageDeleteRequest,
    TicketStatusChangeRequest,
)
from application.queries import TicketDetail
from contracts.ticket import TicketDetailView, TicketView
from domain.repositories import PageInfo
from domain.ticket import Ticket
from infrastructure.security.auth import RequiredActor

router = APIRouter(prefix="/api/v1/tickets", tags=["tickets"])


def _detail_result(result: Result[Ticket]) -> Result[TicketDetailView]:
    if result.is_err:
        return Result[TicketDetailView].fail(result.error)
    ticket = result.value
    return Result[TicketDetailView].ok(TicketDetailView.from_domain(ticket, ticket.messages))


def _view_result(result: Result[Ticket]) -> Result[TicketView]:
    if result.is_err:
        return Result[TicketView].fail(result.error)
    return Result[TicketView].ok(TicketView.from_domain(result.value))


def _null_result(result: Result[Ticket]) -> Result[None]:
    if result.is_err:
        return Result[None].fail(result.error)
    return Result[None].ok(None)


def _unwrap[T](result: Result[T]) -> T:
    """`GetTicketDetailQueryHandler` carries pagination for `meta` alongside
    `data` — a shape `match_result` doesn't fit — so this keeps the same
    error translation without wrapping the success value."""
    if result.is_err:
        error = result.error
        raise ApiError(
            status_code=status_code_for_error_type(error.type),
            code=error.code,
            message=error.description,
        )
    return result.value


def _page_meta(page_info: PageInfo) -> dict[str, object]:
    return {
        "next_cursor": page_info.next_cursor,
        "prev_cursor": page_info.prev_cursor,
        "has_more": page_info.has_more,
        "has_prev": page_info.has_prev,
    }


@router.post(
    "",
    response_model=ApiResponse[TicketDetailView],
    status_code=status.HTTP_201_CREATED,
)
async def create_ticket(
    request: TicketCreateRequest, actor: RequiredActor, handler: CreateTicketDI
) -> ApiResponse[TicketDetailView]:
    result = await handler.execute(request.to_command(actor=actor))
    return match_created(_detail_result(result))


@router.get("", response_model=ApiResponse[list[TicketView]])
async def list_tickets(
    request: Annotated[TicketListRequest, Depends()],
    actor: RequiredActor,
    handler: ListTicketsDI,
) -> ApiResponse[list[TicketView]]:
    page = await handler.execute(request.to_query(actor=actor))
    return ApiResponse(
        data=[TicketView.from_domain(ticket) for ticket in page.items],
        meta=_page_meta(page.page_info),
    )


@router.get("/admin", response_model=ApiResponse[list[TicketView]])
async def list_admin_tickets(
    request: Annotated[AdminTicketListRequest, Depends()],
    actor: RequiredActor,
    handler: ListAdminTicketsDI,
) -> ApiResponse[list[TicketView]]:
    page = _unwrap(await handler.execute(request.to_query(actor=actor)))
    return ApiResponse(
        data=[TicketView.from_domain(ticket) for ticket in page.items],
        meta=_page_meta(page.page_info),
    )


@router.post(
    "/{ticket_id}/messages",
    response_model=ApiResponse[TicketView],
    status_code=status.HTTP_201_CREATED,
)
async def add_ticket_message(
    ticket_id: uuid.UUID,
    request: TicketMessageCreateRequest,
    actor: RequiredActor,
    handler: AddTicketMessageDI,
) -> ApiResponse[TicketView]:
    command = request.to_command(ticket_id=ticket_id, actor=actor)
    result = await handler.execute(command)
    return match_created(_view_result(result))


@router.patch("/{ticket_id}/status", response_model=ApiResponse[TicketView])
async def change_ticket_status(
    ticket_id: uuid.UUID,
    request: TicketStatusChangeRequest,
    actor: RequiredActor,
    handler: ChangeTicketStatusDI,
) -> ApiResponse[TicketView]:
    command = request.to_command(ticket_id=ticket_id, actor=actor)
    result = await handler.execute(command)
    return match_result(_view_result(result))


@router.patch(
    "/{ticket_id}/messages/{message_id}", response_model=ApiResponse[TicketView]
)
async def edit_ticket_message(
    ticket_id: uuid.UUID,
    message_id: uuid.UUID,
    request: TicketMessageCreateRequest,
    actor: RequiredActor,
    handler: EditTicketMessageDI,
) -> ApiResponse[TicketView]:
    command = request.to_edit_command(
        ticket_id=ticket_id, message_id=message_id, actor=actor
    )
    result = await handler.execute(command)
    return match_result(_view_result(result))


@router.delete("/{ticket_id}/messages/{message_id}", response_model=ApiResponse[None])
async def delete_ticket_message(
    request: Annotated[TicketMessageDeleteRequest, Depends()],
    actor: RequiredActor,
    handler: DeleteTicketMessageDI,
) -> ApiResponse[None]:
    result = await handler.execute(request.to_command(actor=actor))
    return match_result(_null_result(result))


@router.get("/{ticket_id}", response_model=ApiResponse[TicketDetailView])
async def get_ticket(
    request: Annotated[TicketDetailRequest, Depends()],
    actor: RequiredActor,
    handler: GetTicketDetailDI,
) -> ApiResponse[TicketDetailView]:
    detail: TicketDetail = _unwrap(await handler.execute(request.to_query(actor=actor)))
    return ApiResponse(data=detail.view, meta=_page_meta(detail.messages_page_info))
