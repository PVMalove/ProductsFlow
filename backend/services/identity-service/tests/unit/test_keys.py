import base64
from pathlib import Path

import pytest
from cryptography.hazmat.primitives.asymmetric import rsa

from identity.infrastructure.security.keys import (
    build_jwk,
    compute_kid,
    load_private_key,
    validate_prod_key,
)
from identity.settings import settings
from tests.unit.keygen import write_rsa_key_file

# Вектор из RFC 7638, приложение A — проверяет compute_kid против эталонного thumbprint.
_RFC7638_N = (
    "0vx7agoebGcQSuuPiLJXZptN9nndrQmbXEps2aiAFbWhM78LhWx4cbbfAAtVT86zwu1RK7"
    "aPFFxuhDR1L6tSoc_BJECPebWKRXjBZCiFV4n3oknjhMstn64tZ_2W-5JsGY4Hc5n9yBXA"
    "rwl93lqt7_RN5w6Cf0h4QyQ5v-65YGjQR0_FDW2QvzqY368QQMicAtaSqzs8KJZgnYb9c7"
    "d0zgdAZHzu6qMQvRL5hajrn1n91CbOpbISD08qNLyrdkt-bFTWhAI4vMQFh6WeZu0fM4lF"
    "d2NcRwr3XPksINHaQ-G_xBniIqbw0Ls1jF44-csFCur-kEgU8awapJzKnqDKgw"
)
_RFC7638_E = "AQAB"
_RFC7638_EXPECTED_KID = "NzbLsXh8uDCcd-6MNwXF4W_7noWXFZAfHkxZsRGC9Xs"


def _b64url_to_uint(value: str) -> int:
    padded = value + "=" * (-len(value) % 4)
    return int.from_bytes(base64.urlsafe_b64decode(padded), "big")


def test_compute_kid_matches_rfc7638_worked_example() -> None:
    public_key = rsa.RSAPublicNumbers(
        e=_b64url_to_uint(_RFC7638_E), n=_b64url_to_uint(_RFC7638_N)
    ).public_key()

    assert compute_kid(public_key) == _RFC7638_EXPECTED_KID


def test_compute_kid_is_deterministic_for_the_same_key(
    configured_key_path: Path,
) -> None:
    private_key = load_private_key(str(configured_key_path))

    assert compute_kid(private_key.public_key()) == compute_kid(
        private_key.public_key()
    )


def test_compute_kid_differs_for_different_keys(
    configured_key_path: Path, tmp_path: Path
) -> None:
    first_key = load_private_key(str(configured_key_path))
    other_path = tmp_path / "other.pem"
    write_rsa_key_file(other_path)
    second_key = load_private_key(str(other_path))

    assert compute_kid(first_key.public_key()) != compute_kid(second_key.public_key())


def test_load_private_key_reuses_the_same_in_memory_key_for_the_same_path(
    configured_key_path: Path,
) -> None:
    """Второй вызов не должен снова читать файл с диска (ADR 0011: "по ключу
    в памяти") — объект, а не только значение, должен быть тем же самым."""
    first = load_private_key(str(configured_key_path))
    second = load_private_key(str(configured_key_path))

    assert first is second


def test_load_private_key_raises_for_missing_file() -> None:
    with pytest.raises(OSError):
        load_private_key(str(Path("no") / "such" / "path.pem"))


def test_load_private_key_raises_for_invalid_pem_content(tmp_path: Path) -> None:
    bad_path = tmp_path / "garbage.pem"
    bad_path.write_text("not a pem file")

    with pytest.raises(ValueError):
        load_private_key(str(bad_path))


def test_build_jwk_contains_expected_fields(configured_key_path: Path) -> None:
    private_key = load_private_key(str(configured_key_path))
    public_key = private_key.public_key()
    kid = compute_kid(public_key)

    jwk = build_jwk(public_key, kid)

    assert jwk == {
        "kty": "RSA",
        "use": "sig",
        "alg": "RS256",
        "kid": kid,
        "n": jwk["n"],
        "e": jwk["e"],
    }
    assert jwk["n"] and jwk["e"]


def test_validate_prod_key_raises_when_path_is_empty_in_prod(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr(settings, "app_env", "prod")
    monkeypatch.setattr(settings, "identity_jwt_private_key_path", "")

    with pytest.raises(RuntimeError):
        validate_prod_key(settings)


def test_validate_prod_key_raises_when_path_is_unreadable_in_prod(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr(settings, "app_env", "prod")
    monkeypatch.setattr(
        settings, "identity_jwt_private_key_path", str(Path("no") / "such" / "file.pem")
    )

    with pytest.raises(RuntimeError):
        validate_prod_key(settings)


def test_validate_prod_key_raises_when_file_content_is_invalid_in_prod(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    bad_path = tmp_path / "garbage.pem"
    bad_path.write_text("not a pem file")
    monkeypatch.setattr(settings, "app_env", "prod")
    monkeypatch.setattr(settings, "identity_jwt_private_key_path", str(bad_path))

    with pytest.raises(RuntimeError):
        validate_prod_key(settings)


def test_validate_prod_key_does_not_raise_in_dev_when_path_is_empty(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr(settings, "app_env", "dev")
    monkeypatch.setattr(settings, "identity_jwt_private_key_path", "")

    validate_prod_key(settings)


def test_validate_prod_key_does_not_raise_in_prod_with_a_valid_key(
    configured_key_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setattr(settings, "app_env", "prod")

    validate_prod_key(settings)
