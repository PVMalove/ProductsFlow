from unittest.mock import AsyncMock

import pytest

from api import worker


@pytest.mark.asyncio
async def test_identity_worker_declares_every_user_event_consumer_before_publishing(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    declare_topology = AsyncMock()
    monkeypatch.setattr(worker, "declare_topology", declare_topology)
    channel = object()

    await worker._declare_user_event_consumer_topology(channel)  # type: ignore[arg-type]

    assert declare_topology.await_args_list == [
        ((channel,), {"service_name": "catalog-service"}),
        ((channel,), {"service_name": "support-service"}),
    ]
