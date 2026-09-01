import logging
from pathlib import Path

import httpx
import jwt
import pytest
from cryptography.hazmat.primitives.asymmetric import rsa
from kernel_platform.security.identity_client import IdentityClient

from core.security.tokens import create_access_token
from presentation.main import app as identity_app
from tests.unit.counting_transport import CountingTransport, FlakyOnceTransport


def _forge_token(kid: str, sub: str = "999") -> str:
    rogue_key = rsa.generate_private_key(public_exponent=65537, key_size=2048)
    return jwt.encode({"sub": sub}, rogue_key, algorithm="RS256", headers={"kid": kid})


async def test_verify_token_accepts_a_token_signed_by_identity(
    identity_http_client: httpx.AsyncClient,
) -> None:
    client = IdentityClient(identity_http_client)
    token = create_access_token(sub=42)

    payload = await client.verify_token(token)

    assert payload["sub"] == "42"
    assert payload["iss"] == "identity-service"


async def test_verify_token_reuses_a_cached_kid_without_an_http_call(
    identity_http_client: httpx.AsyncClient, identity_transport: CountingTransport
) -> None:
    client = IdentityClient(identity_http_client)
    await client.verify_token(create_access_token(sub=1))
    assert identity_transport.request_count == 1

    await client.verify_token(create_access_token(sub=2))

    assert identity_transport.request_count == 1


async def test_verify_token_refetches_once_for_unknown_kid_within_throttle_window(
    identity_http_client: httpx.AsyncClient, identity_transport: CountingTransport
) -> None:
    client = IdentityClient(identity_http_client)
    # Прогреваем кэш реальным kid — дальше запросы бьют именно по "неизвестному kid".
    await client.verify_token(create_access_token(sub=1))
    assert identity_transport.request_count == 1

    bogus_token = _forge_token(kid="bogus-kid")

    with pytest.raises(jwt.InvalidTokenError):
        await client.verify_token(bogus_token)
    assert identity_transport.request_count == 2

    with pytest.raises(jwt.InvalidTokenError):
        await client.verify_token(bogus_token)
    assert identity_transport.request_count == 2


async def test_verify_token_rejects_a_token_signed_by_a_different_key(
    identity_http_client: httpx.AsyncClient,
) -> None:
    client = IdentityClient(identity_http_client)
    real_token = create_access_token(sub=1)
    real_kid = jwt.get_unverified_header(real_token)["kid"]

    forged_token = _forge_token(kid=real_kid, sub="1")

    with pytest.raises(jwt.InvalidSignatureError):
        await client.verify_token(forged_token)


async def test_preload_failure_is_non_fatal_logs_and_lazy_fetch_still_works(
    configured_key_path: Path, caplog: pytest.LogCaptureFixture
) -> None:
    transport = FlakyOnceTransport(httpx.ASGITransport(app=identity_app), fail_times=1)
    async with httpx.AsyncClient(
        transport=transport, base_url="http://identity"
    ) as http_client:
        client = IdentityClient(http_client)

        with caplog.at_level(
            logging.WARNING, logger="kernel_platform.security.identity_client"
        ):
            await client.preload()

        assert "JWKS" in caplog.text

        payload = await client.verify_token(create_access_token(sub=7))

        assert payload["sub"] == "7"
