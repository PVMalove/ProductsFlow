import json
from typing import Any


class FakeUsersMeApp:
    """Минимальный ASGI-стаб GET /api/v1/users/me — не настоящий identity-service
    (у него ещё нет HTTP-роута для этого эндпоинта), только форма ответа из
    контракта ADR 0012 (`id` — GUID `identity.UserId`)."""

    def __init__(
        self, response: dict[str, Any] | None = None, status: int = 200
    ) -> None:
        self._response = response or {
            "id": "00000000-0000-0000-0000-000000000001",
            "role": "user",
            "is_active": True,
        }
        self._status = status
        self.received_authorization: str | None = None

    async def __call__(self, scope: Any, _receive: Any, send: Any) -> None:
        headers = dict(scope["headers"])
        auth = headers.get(b"authorization")
        self.received_authorization = auth.decode() if auth else None

        body = json.dumps(self._response).encode()
        await send(
            {
                "type": "http.response.start",
                "status": self._status,
                "headers": [(b"content-type", b"application/json")],
            }
        )
        await send({"type": "http.response.body", "body": body})
