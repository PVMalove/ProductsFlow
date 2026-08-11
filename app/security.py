from datetime import datetime, timedelta, timezone
from typing import Any

import jwt

ALGORITHM = "HS256"
SECRET_KEY = "9B-Q9MaiLNMzpM2x7fSrLjKvTMkO8yXS2vYvodMqDkmoFLJvCX3fOUFTf_Y2BAU1"
ACCESS_TOKEN_TTL = timedelta(hours=1)

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