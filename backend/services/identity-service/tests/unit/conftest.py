from collections.abc import AsyncIterator
from pathlib import Path

import httpx
import pytest

from core.settings import settings
from presentation.main import app as identity_app
from tests.unit.counting_transport import CountingTransport
from tests.unit.keygen import write_rsa_key_file


@pytest.fixture
def configured_key_path(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> Path:
    key_path = tmp_path / "identity_jwt_private_key.pem"
    write_rsa_key_file(key_path)
    monkeypatch.setattr(settings, "identity_jwt_private_key_path", str(key_path))
    return key_path


@pytest.fixture
def identity_transport(configured_key_path: Path) -> CountingTransport:
    return CountingTransport(httpx.ASGITransport(app=identity_app))


@pytest.fixture
async def identity_http_client(
    identity_transport: CountingTransport,
) -> AsyncIterator[httpx.AsyncClient]:
    async with httpx.AsyncClient(
        transport=identity_transport, base_url="http://identity"
    ) as client:
        yield client
