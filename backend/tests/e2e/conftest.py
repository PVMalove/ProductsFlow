import asyncio
import os
import socket
import subprocess
import time
from collections.abc import AsyncIterator, Iterable
from pathlib import Path
from random import uniform

import httpx
import pytest
import pytest_asyncio

_BACKEND_DIR = Path(__file__).resolve().parents[2]
_COMPOSE_FILES = (
    "docker-compose.yml",
    "docker-compose.e2e.yml",
)
_COMPOSE_PROJECT = "productsflow-e2e"
_ADMIN_EMAIL = "e2e-admin@example.test"
_ADMIN_PASSWORD = "E2e-admin-password-123"
_READINESS_DEADLINE_SECONDS = 30.0
_MIN_RETRY_DELAY_SECONDS = 0.1
_MAX_RETRY_DELAY_SECONDS = 2.0


def _free_tcp_port() -> int:
    with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as listener:
        listener.bind(("127.0.0.1", 0))
        return int(listener.getsockname()[1])


def _compose_command(*args: str) -> list[str]:
    command = ["docker", "compose", "--project-name", _COMPOSE_PROJECT]
    for compose_file in _COMPOSE_FILES:
        command.extend(("--file", compose_file))
    return [*command, *args]


def _run_compose(*args: str, environment: dict[str, str]) -> None:
    result = subprocess.run(
        _compose_command(*args),
        cwd=_BACKEND_DIR,
        env=environment,
        text=True,
        capture_output=True,
        check=False,
    )
    if result.returncode:
        raise RuntimeError(
            f"docker compose {' '.join(args)} failed with {result.returncode}:\n"
            f"stdout:\n{result.stdout}\nstderr:\n{result.stderr}"
        )


async def _wait_for_response(
    client: httpx.AsyncClient,
    *,
    method: str,
    url: str,
    expected_status: int,
    retry_statuses: Iterable[int] = (),
    **request_kwargs: object,
) -> httpx.Response:
    """Poll only explicitly transient outcomes; every other HTTP failure is final."""
    allowed_retries = frozenset(retry_statuses)
    deadline = time.monotonic() + _READINESS_DEADLINE_SECONDS
    delay = _MIN_RETRY_DELAY_SECONDS
    last_body = "<no response received>"

    while True:
        try:
            response = await client.request(method, url, **request_kwargs)
        except httpx.RequestError as error:
            last_body = f"<request error: {error}>"
        else:
            last_body = response.text
            if response.status_code == expected_status:
                return response
            if response.status_code not in allowed_retries:
                pytest.fail(
                    f"{method} {url} returned unexpected {response.status_code}: "
                    f"{last_body}"
                )

        if time.monotonic() >= deadline:
            pytest.fail(
                f"Timed out after {_READINESS_DEADLINE_SECONDS:.0f}s waiting for "
                f"{method} {url} to return {expected_status}; "
                f"last response body: {last_body}"
            )
        await asyncio.sleep(min(_MAX_RETRY_DELAY_SECONDS, delay * uniform(0.8, 1.2)))
        delay = min(_MAX_RETRY_DELAY_SECONDS, delay * 2)


async def _wait_for_ticket_closed(
    client: httpx.AsyncClient, *, url: str, headers: dict[str, str]
) -> dict[str, object]:
    """Poll a ticket-detail response until Support's async user-deletion
    consumer closes it. Unlike `_wait_for_response`, the transient signal
    lives in the response body, not the status code: only a `200` with a
    non-terminal `status` is retried — every other outcome (a non-`200`, or
    a request error) ends the test immediately."""
    deadline = time.monotonic() + _READINESS_DEADLINE_SECONDS
    delay = _MIN_RETRY_DELAY_SECONDS
    last_body = "<no response received>"

    while True:
        response = await client.get(url, headers=headers)
        last_body = response.text
        if response.status_code != 200:
            pytest.fail(
                f"GET {url} returned unexpected {response.status_code}: {last_body}"
            )
        data = response.json()["data"]
        if data["status"] == "CLOSED":
            return data

        if time.monotonic() >= deadline:
            pytest.fail(
                f"Timed out after {_READINESS_DEADLINE_SECONDS:.0f}s waiting for "
                f"{url} to close; last response body: {last_body}"
            )
        await asyncio.sleep(min(_MAX_RETRY_DELAY_SECONDS, delay * uniform(0.8, 1.2)))
        delay = min(_MAX_RETRY_DELAY_SECONDS, delay * 2)


async def _login_seeded_admin(client: httpx.AsyncClient) -> str:
    response = await client.post(
        "/api/v1/auth/login",
        data={"username": _ADMIN_EMAIL, "password": _ADMIN_PASSWORD},
    )
    if response.status_code != 200:
        pytest.fail(
            f"Seeded E2E admin login failed: {response.status_code}: {response.text}"
        )
    return str(response.json()["access_token"])


@pytest_asyncio.fixture(scope="session")
async def gateway_client() -> AsyncIterator[httpx.AsyncClient]:
    port = _free_tcp_port()
    environment = {**os.environ, "E2E_GATEWAY_PORT": str(port)}

    try:
        _run_compose("up", "--build", "--detach", "--wait", environment=environment)
        async with httpx.AsyncClient(
            base_url=f"http://127.0.0.1:{port}",
            timeout=15.0,
            limits=httpx.Limits(max_keepalive_connections=0),
        ) as client:
            await _wait_for_response(
                client,
                method="GET",
                url="/.well-known/jwks.json",
                expected_status=200,
            )
            admin_token = await _login_seeded_admin(client)
            await _wait_for_response(
                client,
                method="GET",
                url="/api/v1/tickets",
                expected_status=200,
                retry_statuses=(401,),
                headers={"Authorization": f"Bearer {admin_token}"},
            )
            yield client
    finally:
        _run_compose("down", "-v", "--remove-orphans", environment=environment)
