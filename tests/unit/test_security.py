import jwt
import pytest

from app.security import (
    ALGORITHM,
    create_access_token,
    decode_access_token,
    hash_password,
    verify_password,
)
from app.settings import settings


def test_verify_password_accepts_the_password_it_was_hashed_from():
    hashed = hash_password("correct-horse-battery-staple")

    assert verify_password("correct-horse-battery-staple", hashed) is True


def test_verify_password_rejects_a_wrong_password():
    hashed = hash_password("correct-horse-battery-staple")

    assert verify_password("wrong-password", hashed) is False


def test_verify_password_rejects_a_malformed_hash_instead_of_raising():
    assert verify_password("any-password", "not-a-bcrypt-hash") is False


def test_hash_password_does_not_return_the_plaintext():
    plaintext = "correct-horse-battery-staple"

    assert hash_password(plaintext) != plaintext


def test_decode_access_token_recovers_the_subject_of_a_freshly_created_token():
    token = create_access_token(sub=42)

    payload = decode_access_token(token)

    assert payload["sub"] == "42"


def test_decode_access_token_rejects_an_expired_token(monkeypatch):
    monkeypatch.setattr(settings, "access_token_ttl_hours", -1)
    token = create_access_token(sub=42)

    with pytest.raises(jwt.ExpiredSignatureError):
        decode_access_token(token)


def test_decode_access_token_rejects_a_token_signed_with_a_different_secret():
    forged_token = jwt.encode({"sub": "42"}, "a-different-secret", algorithm=ALGORITHM)

    with pytest.raises(jwt.InvalidSignatureError):
        decode_access_token(forged_token)


def test_decode_access_token_rejects_garbage_input():
    with pytest.raises(jwt.PyJWTError):
        decode_access_token("not-a-jwt-at-all")
