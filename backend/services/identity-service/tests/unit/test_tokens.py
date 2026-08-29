from pathlib import Path

import jwt
import pytest

from identity.infrastructure.security.keys import compute_kid, load_private_key
from identity.infrastructure.security.tokens import (
    ALGORITHM,
    ISSUER,
    create_access_token,
    decode_access_token,
)
from identity.settings import settings
from tests.unit.keygen import write_rsa_key_file

pytestmark = pytest.mark.usefixtures("configured_key_path")


def test_decode_access_token_recovers_the_subject_of_a_freshly_created_token() -> None:
    token = create_access_token(sub=42)

    payload = decode_access_token(token)

    assert payload["sub"] == "42"


def test_create_access_token_includes_expected_claims_and_no_audience() -> None:
    token = create_access_token(sub=1)

    payload = decode_access_token(token)

    assert payload.keys() == {"sub", "iat", "exp", "iss"}
    assert payload["iss"] == ISSUER


def test_create_access_token_header_kid_matches_the_signing_key_thumbprint() -> None:
    token = create_access_token(sub=1)
    private_key = load_private_key(settings.identity_jwt_private_key_path)

    header = jwt.get_unverified_header(token)

    assert header["kid"] == compute_kid(private_key.public_key())


def test_decode_access_token_rejects_an_expired_token(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr(settings, "identity_access_token_ttl_hours", -1)
    token = create_access_token(sub=42)

    with pytest.raises(jwt.ExpiredSignatureError):
        decode_access_token(token)


def test_decode_access_token_rejects_a_token_signed_with_a_different_key(
    tmp_path: Path,
) -> None:
    other_key_path = tmp_path / "other.pem"
    write_rsa_key_file(other_key_path)
    other_private_key = load_private_key(str(other_key_path))
    forged_token = jwt.encode({"sub": "42"}, other_private_key, algorithm=ALGORITHM)

    with pytest.raises(jwt.InvalidSignatureError):
        decode_access_token(forged_token)


def test_decode_access_token_rejects_garbage_input() -> None:
    with pytest.raises(jwt.PyJWTError):
        decode_access_token("not-a-jwt-at-all")
