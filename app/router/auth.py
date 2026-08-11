from fastapi import APIRouter

router = APIRouter(prefix="/auth", tags=["auth"])

@router.get("/login")
async def login() -> dict[str, str]:
    return {"message": "Login endpoint"}
