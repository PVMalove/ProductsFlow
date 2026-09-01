from fastapi import APIRouter, status

from api.dependencies import CreateTicketDI
from api.schemas import TicketCreateRequest, TicketResponse
from infrastructure.security.auth import RequiredAuth

router = APIRouter(prefix="/api/v1/tickets", tags=["tickets"])


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
