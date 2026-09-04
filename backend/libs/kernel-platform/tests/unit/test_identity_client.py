# ruff: noqa: E501
import uuid

import httpx
import pytest

from kernel_platform.security.identity_client import IdentityClient
from tests.unit.counting_transport import CountingTransport, FlakyOnceTransport
from tests.unit.fake_users_me_app import FakeUsersMeApp


async def test_fetch_current_user_returns_the_three_contract_fields() -> None:
    user_id = uuid.uuid4()
    app = FakeUsersMeApp(
        response={"id": str(user_id), "role": "admin", "is_active": True}
    )
    async with httpx.AsyncClient(
        transport=httpx.ASGITransport(app=app), base_url="http://identity"
    ) as http_client:
        client = IdentityClient(http_client)

        info = await client.fetch_current_user("some-token")

        assert info.id == user_id
        assert info.role == "admin"
    assert info.is_active is True


async def test_fetch_current_user_unwraps_the_bff_success_envelope() -> None:
    user_id = uuid.uuid4()
    app = FakeUsersMeApp(
        response={
            "data": {"id": str(user_id), "role": "user", "is_active": True},
            "meta": {},
        }
    )
    async with httpx.AsyncClient(
        transport=httpx.ASGITransport(app=app), base_url="http://identity"
    ) as http_client:
        client = IdentityClient(http_client)

        info = await client.fetch_current_user("some-token")

        assert info.id == user_id
        assert info.role == "user"
        assert info.is_active is True


async def test_fetch_current_user_forwards_the_bearer_token() -> None:
    app = FakeUsersMeApp()
    async with httpx.AsyncClient(
        transport=httpx.ASGITransport(app=app), base_url="http://identity"
    ) as http_client:
        client = IdentityClient(http_client)

        await client.fetch_current_user("caller-token")

        assert app.received_authorization == "Bearer caller-token"


async def test_fetch_current_user_propagates_identity_failure() -> None:
    app = FakeUsersMeApp(status=500)
    async with httpx.AsyncClient(
        transport=httpx.ASGITransport(app=app), base_url="http://identity"
    ) as http_client:
        client = IdentityClient(http_client)

        with pytest.raises(httpx.HTTPStatusError):
            await client.fetch_current_user("some-token")


async def test_fetch_current_user_propagates_a_connection_error() -> None:
    app = FakeUsersMeApp()
    transport = FlakyOnceTransport(httpx.ASGITransport(app=app), fail_times=1)
    async with httpx.AsyncClient(
        transport=transport, base_url="http://identity"
    ) as http_client:
        client = IdentityClient(http_client)

        with pytest.raises(httpx.ConnectError):
            await client.fetch_current_user("some-token")


async def test_fetch_current_user_never_caches_across_calls() -> None:
    app = FakeUsersMeApp()
    transport = CountingTransport(httpx.ASGITransport(app=app))
    async with httpx.AsyncClient(
        transport=transport, base_url="http://identity"
    ) as http_client:
        client = IdentityClient(http_client)

        await client.fetch_current_user("some-token")
        await client.fetch_current_user("some-token")

        assert transport.request_count == 2
