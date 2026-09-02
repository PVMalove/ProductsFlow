from uuid import UUID

import jwt
import pytest

from core.security.tokens import create_access_token
from core.security.verifier import LocalTokenVerifier

pytestmark = pytest.mark.usefixtures("configured_key_path")

_SUBJECT = UUID("00000000-0000-0000-0000-000000000042")


async def test_verify_token_recovers_the_subject_of_a_valid_token() -> None:
    token = create_access_token(sub=_SUBJECT)

    payload = await LocalTokenVerifier().verify_token(token)

    assert payload["sub"] == str(_SUBJECT)


async def test_verify_token_raises_on_garbage_input() -> None:
    with pytest.raises(jwt.PyJWTError):
        await LocalTokenVerifier().verify_token("not-a-jwt-at-all")
