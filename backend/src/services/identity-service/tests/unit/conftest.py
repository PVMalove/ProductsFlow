from pathlib import Path

import pytest
from identity_service.settings import settings

from tests.unit.keygen import write_rsa_key_file


@pytest.fixture
def configured_key_path(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> Path:
    key_path = tmp_path / "identity_jwt_private_key.pem"
    write_rsa_key_file(key_path)
    monkeypatch.setattr(settings, "identity_jwt_private_key_path", str(key_path))
    return key_path
