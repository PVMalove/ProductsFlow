"""infrastructure/psp/mock_psp_adapter.py (issue #368, Seams for TDD #1):
таблица соответствий токен→исход, чистая функция, без I/O, без рандома."""

import pytest

from domain.psp_client import (
    PspAuthorizeOutcome,
    PspCaptureLookupOutcome,
    PspCaptureOutcome,
    UnknownPspScenarioTokenError,
)
from infrastructure.psp.mock_psp_adapter import MockPspAdapter


async def test_authorize_success_token_returns_success_outcome() -> None:
    adapter = MockPspAdapter()

    outcome = await adapter.authorize("success", 1000)

    assert outcome is PspAuthorizeOutcome.SUCCESS


async def test_authorize_decline_token_returns_decline_outcome() -> None:
    adapter = MockPspAdapter()

    outcome = await adapter.authorize("decline", 1000)

    assert outcome is PspAuthorizeOutcome.DECLINE


async def test_authorize_timeout_token_returns_timeout_outcome() -> None:
    adapter = MockPspAdapter()

    outcome = await adapter.authorize("timeout", 1000)

    assert outcome is PspAuthorizeOutcome.TIMEOUT


async def test_authorize_unknown_capture_token_authorizes_successfully() -> None:
    """`unknown_capture` селектор только про исход capture — authorize должен
    дойти до AUTHORIZED, иначе capture никогда не станет тестируемым (брифа D4)."""
    adapter = MockPspAdapter()

    outcome = await adapter.authorize("unknown_capture", 1000)

    assert outcome is PspAuthorizeOutcome.SUCCESS


async def test_authorize_unrecognized_token_raises() -> None:
    adapter = MockPspAdapter()

    with pytest.raises(UnknownPspScenarioTokenError):
        await adapter.authorize("not-a-real-scenario", 1000)


async def test_capture_success_token_returns_captured_outcome() -> None:
    adapter = MockPspAdapter()

    outcome = await adapter.capture("success", "capture-key-1")

    assert outcome is PspCaptureOutcome.CAPTURED


async def test_capture_unknown_capture_token_returns_unknown_outcome() -> None:
    adapter = MockPspAdapter()

    outcome = await adapter.capture("unknown_capture", "capture-key-1")

    assert outcome is PspCaptureOutcome.UNKNOWN


async def test_capture_unrecognized_token_raises() -> None:
    adapter = MockPspAdapter()

    with pytest.raises(UnknownPspScenarioTokenError):
        await adapter.capture("not-a-real-scenario", "capture-key-1")


@pytest.mark.parametrize("token", ["success", "unknown_capture"])
async def test_lookup_capture_finds_the_capture_the_psp_recorded(token: str) -> None:
    """Issue #374, brief D3: in the `unknown_capture` scenario the Test PSP did
    record the capture (ADR 0016) — only the response was lost."""
    adapter = MockPspAdapter()

    outcome = await adapter.lookup_capture(token, "capture-key-1")

    assert outcome is PspCaptureLookupOutcome.CAPTURED


@pytest.mark.parametrize("token", ["decline", "timeout", "not-a-real-scenario"])
async def test_lookup_capture_of_a_token_without_a_capture_scenario_raises(
    token: str,
) -> None:
    adapter = MockPspAdapter()

    with pytest.raises(UnknownPspScenarioTokenError):
        await adapter.lookup_capture(token, "capture-key-1")
