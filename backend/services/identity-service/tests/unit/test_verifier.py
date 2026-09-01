import jwt
import pytest

from core.security.tokens import create_access_token
from core.security.verifier import LocalTokenVerifier

pytestmark = pytest.mark.usefixtures("configured_key_path")


async def test_verify_token_recovers_the_subject_of_a_valid_token() -> None:
    token = create_access_token(sub=42)

    payload = await LocalTokenVerifier().verify_token(token)

    assert payload["sub"] == "42"


async def test_verify_token_raises_on_garbage_input() -> None:
    with pytest.raises(jwt.PyJWTError):
        await LocalTokenVerifier().verify_token("not-a-jwt-at-all")
