from fastapi import APIRouter, status

from app.repository import UserRepositoryDI
from app.schemas import UserCreate, UserResponse

router = APIRouter(prefix="/auth", tags=["auth"])

@router.post("/register",
             response_model=UserResponse,
             status_code=status.HTTP_201_CREATED,
             )
async def register_user(request: UserCreate, repository: UserRepositoryDI):
    return await repository.create(request)
