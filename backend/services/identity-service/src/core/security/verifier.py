from typing import Any

from core.security.tokens import decode_access_token


class LocalTokenVerifier:
    """Async-адаптер над decode_access_token под протокол TokenVerifier из
    kernel-platform (ADR 0016, issue #120). decode_access_token не переписан
    и не уходит в threadpool — ключ уже в памяти (lru_cache в keys.py),
    декодирование не делает I/O."""

    async def verify_token(self, token: str) -> dict[str, Any]:
        return decode_access_token(token)
