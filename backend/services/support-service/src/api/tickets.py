import uuid

from fastapi import APIRouter, HTTPException, Query, status

from api.dependencies import (
    AddTicketMessageDI,
    ChangeTicketStatusDI,
    CreateTicketDI,
    DeleteTicketMessageDI,
    EditTicketMessageDI,
    GetTicketDI,
    ListAdminTicketsDI,
    ListTicketMessagesDI,
    ListTicketsDI,
)
from api.schemas import (
    TicketCreateRequest,
    TicketListResponse,
    TicketMessageCreateRequest,
    TicketResponse,
    TicketStatusChangeRequest,
)
from application.commands import (
    AddTicketMessageCommand,
    ChangeTicketStatusCommand,
    CreateTicketCommand,
    DeleteTicketMessageCommand,
    EditTicketMessageCommand,
)
from application.errors import TicketNotFoundError
from application.pagination import (
    DEFAULT_PAGE_LIMIT,
    MAX_PAGE_LIMIT,
    InvalidCursorError,
    decode_cursor,
)
from application.queries import (
    GetTicketQuery,
    ListAdminTicketsQuery,
    ListTicketMessagesQuery,
    ListTicketsQuery,
)
from domain.ticket import (
    InvalidStatusTransitionError,
    TicketClosedError,
    TicketMessageAlreadyDeletedError,
    TicketMessageImmutableError,
    TicketMessageNotFoundError,
)
from infrastructure.security.auth import AdminAuth, OptionalAdmin, RequiredAuth

router = APIRouter(prefix="/api/v1/tickets", tags=["tickets"])


def _cursor(raw: str | None):
    if raw is None:
        return None
    try:
        return decode_cursor(raw)
    except InvalidCursorError as exc:
        raise HTTPException(
            status_code=400, detail="Некорректный курсор пагинации"
        ) from exc


def _ensure_one_cursor(after: str | None, before: str | None) -> None:
    if after is not None and before is not None:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Нельзя одновременно указать after и before",
        )


@router.post("", response_model=TicketResponse, status_code=status.HTTP_201_CREATED)
async def create_ticket(
    request: TicketCreateRequest,
    author_id: RequiredAuth,
    handler: CreateTicketDI,
) -> TicketResponse:
    ticket = await handler.execute(
        CreateTicketCommand(
            author_id=author_id,
            subject=request.subject,
            first_message=request.first_message,
        )
    )
    return TicketResponse.from_domain(ticket)


@router.get("", response_model=TicketListResponse)
async def list_tickets(
    author_id: RequiredAuth,
    handler: ListTicketsDI,
    limit: int = Query(DEFAULT_PAGE_LIMIT, ge=1, le=MAX_PAGE_LIMIT),
    after: str | None = Query(None),
    before: str | None = Query(None),
) -> TicketListResponse:
    _ensure_one_cursor(after, before)
    page = await handler.execute(
        ListTicketsQuery(
            author_id=author_id,
            limit=limit,
            after=_cursor(after),
            before=_cursor(before),
        )
    )
    return TicketListResponse.from_domain(page)


@router.get("/admin", response_model=TicketListResponse)
async def list_admin_tickets(
    _admin_id: AdminAuth,
    handler: ListAdminTicketsDI,
    limit: int = Query(DEFAULT_PAGE_LIMIT, ge=1, le=MAX_PAGE_LIMIT),
    after: str | None = Query(None),
    before: str | None = Query(None),
) -> TicketListResponse:
    _ensure_one_cursor(after, before)
    page = await handler.execute(
        ListAdminTicketsQuery(limit=limit, after=_cursor(after), before=_cursor(before))
    )
    return TicketListResponse.from_domain(page)


@router.post(
    "/{ticket_id}/messages",
    response_model=TicketResponse,
    status_code=status.HTTP_201_CREATED,
)
async def add_ticket_message(
    ticket_id: uuid.UUID,
    request: TicketMessageCreateRequest,
    actor_id: RequiredAuth,
    is_admin: OptionalAdmin,
    handler: AddTicketMessageDI,
) -> TicketResponse:
    try:
        ticket = await handler.execute(
            AddTicketMessageCommand(
                ticket_id=ticket_id,
                actor_id=actor_id,
                body=request.body,
                is_admin=is_admin,
            )
        )
    except TicketNotFoundError as exc:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND, detail="Тикет не найден"
        ) from exc
    except TicketClosedError as exc:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail="Закрытый тикет нельзя изменять",
        ) from exc
    return TicketResponse.from_domain(ticket)


@router.patch("/{ticket_id}/status", response_model=TicketResponse)
async def change_ticket_status(
    ticket_id: uuid.UUID,
    request: TicketStatusChangeRequest,
    admin_id: AdminAuth,
    handler: ChangeTicketStatusDI,
) -> TicketResponse:
    try:
        ticket = await handler.execute(
            ChangeTicketStatusCommand(
                ticket_id=ticket_id,
                actor_id=admin_id,
                status=request.status,
            )
        )
    except TicketNotFoundError as exc:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND, detail="Тикет не найден"
        ) from exc
    except (TicketClosedError, InvalidStatusTransitionError) as exc:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail="Недопустимый переход статуса тикета",
        ) from exc
    return TicketResponse.from_domain(ticket)


@router.patch("/{ticket_id}/messages/{message_id}", response_model=TicketResponse)
async def edit_ticket_message(
    ticket_id: uuid.UUID,
    message_id: uuid.UUID,
    request: TicketMessageCreateRequest,
    actor_id: RequiredAuth,
    is_admin: OptionalAdmin,
    handler: EditTicketMessageDI,
) -> TicketResponse:
    try:
        ticket = await handler.execute(
            EditTicketMessageCommand(
                ticket_id=ticket_id,
                message_id=message_id,
                actor_id=actor_id,
                body=request.body,
                is_admin=is_admin,
            )
        )
    except (TicketNotFoundError, TicketMessageNotFoundError) as exc:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND, detail="Тикет не найден"
        ) from exc
    except (
        TicketClosedError,
        TicketMessageAlreadyDeletedError,
        TicketMessageImmutableError,
    ) as exc:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail="Сообщение нельзя изменить",
        ) from exc
    return TicketResponse.from_domain(ticket)


@router.delete("/{ticket_id}/messages/{message_id}", response_model=TicketResponse)
async def delete_ticket_message(
    ticket_id: uuid.UUID,
    message_id: uuid.UUID,
    actor_id: RequiredAuth,
    is_admin: OptionalAdmin,
    handler: DeleteTicketMessageDI,
) -> TicketResponse:
    try:
        ticket = await handler.execute(
            DeleteTicketMessageCommand(
                ticket_id=ticket_id,
                message_id=message_id,
                actor_id=actor_id,
                is_admin=is_admin,
            )
        )
    except (TicketNotFoundError, TicketMessageNotFoundError) as exc:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND, detail="Тикет не найден"
        ) from exc
    except (
        TicketClosedError,
        TicketMessageAlreadyDeletedError,
        TicketMessageImmutableError,
    ) as exc:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail="Сообщение нельзя удалить",
        ) from exc
    return TicketResponse.from_domain(ticket)


@router.get("/{ticket_id}", response_model=TicketResponse)
async def get_ticket(
    ticket_id: uuid.UUID,
    author_id: RequiredAuth,
    handler: GetTicketDI,
    is_admin: OptionalAdmin,
    messages_handler: ListTicketMessagesDI,
    limit: int = Query(DEFAULT_PAGE_LIMIT, ge=1, le=MAX_PAGE_LIMIT),
    after: str | None = Query(None),
    before: str | None = Query(None),
) -> TicketResponse:
    _ensure_one_cursor(after, before)
    ticket = await handler.execute(
        GetTicketQuery(ticket_id=ticket_id, author_id=author_id, is_admin=is_admin)
    )
    if ticket is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND, detail="Тикет не найден"
        )
    page = await messages_handler.execute(
        ListTicketMessagesQuery(
            ticket_id=ticket_id,
            limit=limit,
            after=_cursor(after),
            before=_cursor(before),
        )
    )
    from api.schemas import PageInfoResponse

    return TicketResponse.from_domain(
        ticket,
        page_info=PageInfoResponse.from_domain(page.page_info),
        messages=page.items,
    )
