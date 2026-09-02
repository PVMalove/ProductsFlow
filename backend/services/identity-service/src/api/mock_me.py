from fastapi import APIRouter

router = APIRouter()


@router.get("/api/v1/users/me")
async def get_users_me():
    return {
        "id": "00000000-0000-0000-0000-000000000001",
        "role": "user",
        "is_active": True,
    }
