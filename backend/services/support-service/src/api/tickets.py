import uuid

from fastapi import APIRouter, HTTPException, Query, status

from api.dependencies import (
    CreateTicketDI,
    GetTicketDI,
    ListAdminTicketsDI,
    ListTicketsDI,
)
from api.schemas import TicketCreateRequest, TicketListResponse, TicketResponse
from application.pagination import (
    DEFAULT_PAGE_LIMIT,
    MAX_PAGE_LIMIT,
    InvalidCursorError,
    decode_cursor,
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
    use_case: CreateTicketDI,
) -> TicketResponse:
    ticket = await use_case.execute(
        author_id=author_id,
        subject=request.subject,
        first_message=request.first_message,
    )
    return TicketResponse.from_domain(ticket)


@router.get("", response_model=TicketListResponse)
async def list_tickets(
    author_id: RequiredAuth,
    use_case: ListTicketsDI,
    limit: int = Query(DEFAULT_PAGE_LIMIT, ge=1, le=MAX_PAGE_LIMIT),
    after: str | None = Query(None),
    before: str | None = Query(None),
) -> TicketListResponse:
    _ensure_one_cursor(after, before)
    page = await use_case.execute(
        author_id=author_id, limit=limit, after=_cursor(after), before=_cursor(before)
    )
    return TicketListResponse.from_domain(page)


@router.get("/admin", response_model=TicketListResponse)
async def list_admin_tickets(
    _admin_id: AdminAuth,
    use_case: ListAdminTicketsDI,
    limit: int = Query(DEFAULT_PAGE_LIMIT, ge=1, le=MAX_PAGE_LIMIT),
    after: str | None = Query(None),
    before: str | None = Query(None),
) -> TicketListResponse:
    _ensure_one_cursor(after, before)
    page = await use_case.execute(
        author_id=_admin_id, limit=limit, after=_cursor(after), before=_cursor(before)
    )
    return TicketListResponse.from_domain(page)


@router.get("/{ticket_id}", response_model=TicketResponse)
async def get_ticket(
    ticket_id: uuid.UUID,
    author_id: RequiredAuth,
    use_case: GetTicketDI,
    is_admin: OptionalAdmin,
    limit: int = Query(DEFAULT_PAGE_LIMIT, ge=1, le=MAX_PAGE_LIMIT),
    after: str | None = Query(None),
    before: str | None = Query(None),
) -> TicketResponse:
    _ensure_one_cursor(after, before)
    ticket = await use_case.execute(
        ticket_id=ticket_id, author_id=author_id, is_admin=is_admin
    )
    if ticket is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND, detail="Тикет не найден"
        )
    page = await use_case.messages(
        ticket_id=ticket_id,
        limit=limit,
        after=_cursor(after),
        before=_cursor(before),
    )
    ticket.messages = page.items
    from api.schemas import PageInfoResponse

    return TicketResponse.from_domain(
        ticket, page_info=PageInfoResponse.from_domain(page.page_info)
    )
