from collections.abc import AsyncIterator
from pathlib import Path

import httpx
import pytest
from identity_service.infrastructure.security.keys import generate_private_key_pem
from identity_service.main import app as identity_app
from identity_service.settings import settings as identity_settings

from tests.unit.counting_transport import CountingTransport


@pytest.fixture
def configured_identity_key(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> Path:
    """Своя пара ключей на тест (уникальный tmp_path) — identity_service.settings
    - модульный синглтон, поэтому путь подменяется через monkeypatch."""
    key_path = tmp_path / "identity_jwt_private_key.pem"
    key_path.write_bytes(generate_private_key_pem())
    monkeypatch.setattr(
        identity_settings, "identity_jwt_private_key_path", str(key_path)
    )
    return key_path


@pytest.fixture
def identity_transport(configured_identity_key: Path) -> CountingTransport:
    return CountingTransport(httpx.ASGITransport(app=identity_app))


@pytest.fixture
async def identity_http_client(
    identity_transport: CountingTransport,
) -> AsyncIterator[httpx.AsyncClient]:
    async with httpx.AsyncClient(
        transport=identity_transport, base_url="http://identity"
    ) as client:
        yield client
