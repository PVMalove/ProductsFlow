from datetime import UTC, datetime, timedelta
from typing import Annotated, Any

import bcrypt
import jwt
from fastapi import Depends, HTTPException, status
from fastapi.security import OAuth2PasswordBearer

from app.models import User, UserRole
from app.repository import UserRepository, UserRepositoryDI
from app.settings import settings

ALGORITHM = "HS256"

oauth2_scheme = OAuth2PasswordBearer(tokenUrl="/auth/login")
# auto_error=False: без заголовка — None, а не 401 (см. ниже).
oauth2_scheme_optional = OAuth2PasswordBearer(tokenUrl="/auth/login", auto_error=False)


def create_access_token(sub: int) -> str:
    now = datetime.now(UTC)
    payload: dict[str, Any] = {
        "sub": str(sub),
        "iat": int(now.timestamp()),
        "exp": int(
            (now + timedelta(hours=settings.access_token_ttl_hours)).timestamp()
        ),
    }
    return jwt.encode(payload, settings.secret_key, algorithm=ALGORITHM)


def decode_access_token(token: str) -> dict[str, Any]:
    return jwt.decode(token, settings.secret_key, algorithms=ALGORITHM)


async def _authenticate(token: str, repo: UserRepository) -> User:
    credentials_exc = HTTPException(
        status_code=status.HTTP_401_UNAUTHORIZED,
        detail="Не удалось проверить токен",
        headers={"WWW-Authenticate": "Bearer"},
    )
    try:
        payload = decode_access_token(token)
        sub_raw = payload.get("sub")
        if sub_raw is None:
            raise credentials_exc
        user_id = int(sub_raw)
    except (jwt.PyJWTError, ValueError) as exc:
        raise credentials_exc from exc

    user = await repo.get_user_by_id(user_id)
    if user is None:
        raise credentials_exc
    if not user.is_active:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Учётная запись отключена",
        )
    return user


async def get_current_user(
    token: Annotated[str, Depends(oauth2_scheme)],
    repo: UserRepositoryDI,
) -> User:
    return await _authenticate(token, repo)


async def get_optional_current_user(
    token: Annotated[str | None, Depends(oauth2_scheme_optional)],
    repo: UserRepositoryDI,
) -> User | None:
    # Невалидный/чужой токен не откатывается на анонимный просмотр (ADR 0002).
    if token is None:
        return None
    return await _authenticate(token, repo)


def hash_password(plain_password: str) -> str:
    return bcrypt.hashpw(plain_password.encode("utf-8"), bcrypt.gensalt()).decode(
        "utf-8"
    )


def verify_password(plain_password: str, hashed_password: str) -> bool:
    try:
        return bcrypt.checkpw(
            plain_password.encode("utf-8"), hashed_password.encode("utf-8")
        )
    except ValueError:
        return False


CurrentUser = Annotated[User, Depends(get_current_user)]
OptionalUser = Annotated[User | None, Depends(get_optional_current_user)]


async def require_admin(user: CurrentUser) -> User:
    if user.role != UserRole.ADMIN:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Доступ только для администраторов!",
        )
    return user


AdminUser = Annotated[User, Depends(require_admin)]
