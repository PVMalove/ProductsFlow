from pathlib import Path

import httpx
import jwt
import pytest
from cryptography.hazmat.primitives.asymmetric import rsa
from identity_service.infrastructure.security.tokens import create_access_token
from identity_service.main import app as identity_app
from kernel_platform.security.token_verifier import TokenVerifier

from tests.unit.counting_transport import CountingTransport, FlakyOnceTransport


def _forge_token(kid: str, sub: str = "999") -> str:
    rogue_key = rsa.generate_private_key(public_exponent=65537, key_size=2048)
    return jwt.encode({"sub": sub}, rogue_key, algorithm="RS256", headers={"kid": kid})


async def test_verify_accepts_a_token_signed_by_identity(
    identity_http_client: httpx.AsyncClient,
) -> None:
    verifier = TokenVerifier(identity_http_client)
    token = create_access_token(sub=42)

    payload = await verifier.verify(token)

    assert payload["sub"] == "42"
    assert payload["iss"] == "identity-service"


async def test_verify_reuses_a_cached_kid_without_an_http_call(
    identity_http_client: httpx.AsyncClient, identity_transport: CountingTransport
) -> None:
    verifier = TokenVerifier(identity_http_client)
    await verifier.verify(create_access_token(sub=1))
    assert identity_transport.request_count == 1

    await verifier.verify(create_access_token(sub=2))

    assert identity_transport.request_count == 1


async def test_verify_refetches_exactly_once_for_unknown_kid_within_throttle_window(
    identity_http_client: httpx.AsyncClient, identity_transport: CountingTransport
) -> None:
    verifier = TokenVerifier(identity_http_client)
    # Прогреваем кэш реальным kid — дальше запросы бьют именно по "неизвестному kid".
    await verifier.verify(create_access_token(sub=1))
    assert identity_transport.request_count == 1

    bogus_token = _forge_token(kid="bogus-kid")

    with pytest.raises(jwt.InvalidTokenError):
        await verifier.verify(bogus_token)
    assert identity_transport.request_count == 2

    with pytest.raises(jwt.InvalidTokenError):
        await verifier.verify(bogus_token)
    assert identity_transport.request_count == 2


async def test_verify_rejects_a_token_signed_by_a_different_key(
    identity_http_client: httpx.AsyncClient,
) -> None:
    verifier = TokenVerifier(identity_http_client)
    real_token = create_access_token(sub=1)
    real_kid = jwt.get_unverified_header(real_token)["kid"]

    forged_token = _forge_token(kid=real_kid, sub="1")

    with pytest.raises(jwt.InvalidSignatureError):
        await verifier.verify(forged_token)


async def test_preload_failure_is_non_fatal_and_lazy_fetch_still_works(
    configured_identity_key: Path,
) -> None:
    transport = FlakyOnceTransport(httpx.ASGITransport(app=identity_app), fail_times=1)
    async with httpx.AsyncClient(
        transport=transport, base_url="http://identity"
    ) as http_client:
        verifier = TokenVerifier(http_client)

        await verifier.preload()

        payload = await verifier.verify(create_access_token(sub=7))

        assert payload["sub"] == "7"
