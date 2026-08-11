from datetime import datetime, timedelta, timezone
from typing import Annotated, Any

import jwt
from fastapi import Depends, HTTPException, status
from fastapi.security import OAuth2PasswordBearer

from app.models import User
from app.repository import UserRepositoryDI

ALGORITHM = "HS256"
SECRET_KEY = "9B-Q9MaiLNMzpM2x7fSrLjKvTMkO8yXS2vYvodMqDkmoFLJvCX3fOUFTf_Y2BAU1"
ACCESS_TOKEN_TTL = timedelta(hours=1)

oauth2_scheme = OAuth2PasswordBearer(tokenUrl="/auth/login")

def create_access_token(sub: int) -> str:
    now = datetime.now(timezone.utc)
    payload: dict[str, Any] = {
        "sub": str(sub),
        "iat": int(now.timestamp()),
        "exp": int((now + ACCESS_TOKEN_TTL).timestamp()),
    }
    return jwt.encode(payload, SECRET_KEY, algorithm=ALGORITHM)


def decode_access_token(token: str) -> dict[str, Any]:
    return jwt.decode(token, SECRET_KEY, algorithms=ALGORITHM)


async def get_current_user(
        token: Annotated[str, Depends(oauth2_scheme)],
        repo: UserRepositoryDI,
) -> User:
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
    except Exception:
        raise credentials_exc

    user = await repo.get_user_by_id(user_id)
    if user is None:
        raise credentials_exc
    if not user.is_active:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Учётная запись отключена",
        )
    return user


CurrentUser = Annotated[User, Depends(get_current_user)]