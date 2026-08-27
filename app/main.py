import logging
from collections.abc import AsyncGenerator
from contextlib import asynccontextmanager
from contextvars import Token
from typing import Any

import jwt
from fastapi import APIRouter, FastAPI, Request, Response
from starlette.middleware.base import RequestResponseEndpoint

from app.audit import current_actor_id
from app.db import engine, run_migrations, seed_db
from app.errors import register_exception_handlers
from app.logging_config import configure_logging
from app.routers import auth, categories, product_images, products, users
from app.security import decode_access_token
from app.settings import settings
from app.storage import ensure_minio_buckets
from app.support import router_admin as support_admin
from app.support import router_user as support_user

configure_logging()
logger = logging.getLogger(__name__)


@asynccontextmanager
async def lifespan(app: FastAPI) -> AsyncGenerator[None, None]:
    logger.info("Запуск ProductsFlow API")
    await run_migrations()
    await ensure_minio_buckets()
    await seed_db()
    yield
    await engine.dispose()


app = FastAPI(
    title=f"ProductsFlow API [{settings.app_env.lower()}]",
    description=(
        "Сервис учёта товаров: аутентификация пользователей, "
        "CRUD-операции над товарами и управление пользователями."
    ),
    lifespan=lifespan,
)
app_v1 = APIRouter(prefix="/api/v1")
app.include_router(app_v1)
app_v1.include_router(auth.router)
app_v1.include_router(products.router)
app_v1.include_router(users.router)
app_v1.include_router(support_user.router)
app_v1.include_router(support_admin.router)

app_v2 = APIRouter(prefix="/api/v2")
app.include_router(app_v2)
app_v2.include_router(product_images.router)
app_v2.include_router(categories.router)

register_exception_handlers(app)


@app.middleware("http")
async def actor_context_middleware(
    request: Request,
    call_next: RequestResponseEndpoint,
) -> Response:
    actor_id: int | None = None
    auth_header: str = request.headers.get("authorization", "")

    if auth_header.lower().startswith("bearer "):
        try:
            payload: dict[str, Any] = decode_access_token(auth_header[7:])
            sub_raw: Any | None = payload.get("sub")
            if sub_raw is not None:
                actor_id = int(sub_raw)
        except jwt.PyJWTError, ValueError:
            pass

    reset_token: Token[int | None] | None = (
        current_actor_id.set(actor_id) if actor_id else None
    )
    try:
        return await call_next(request)
    finally:
        if reset_token is not None:
            current_actor_id.reset(reset_token)


@app.get("/health")
async def health_check() -> dict[str, str]:
    return {"status": "ok"}
