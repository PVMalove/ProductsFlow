import json
import uuid
from typing import cast

import pytest
from aio_pika.abc import AbstractIncomingMessage

from api.search_worker import (
    handle_owner_event,
    handle_product_event,
    handle_search_event,
)
from application.ports import OwnerSearchState
from application.search_snapshot import ProductSearchSnapshot


class FakeMessage:
    def __init__(
        self,
        *,
        event_type: str,
        payload: dict[str, object],
        message_id: str | None = None,
    ) -> None:
        self.type = event_type
        self.routing_key = event_type
        self.body = json.dumps(payload).encode()
        self.message_id = message_id


class RecordingIndexer:
    def __init__(self) -> None:
        self.snapshots: list[tuple[ProductSearchSnapshot, bool]] = []
        self.owner_updates: list[tuple[uuid.UUID, bool]] = []

    async def index(
        self, snapshot: ProductSearchSnapshot, *, owner_is_active: bool
    ) -> None:
        self.snapshots.append((snapshot, owner_is_active))

    async def set_owner_active(self, user_id: uuid.UUID, *, is_active: bool) -> None:
        self.owner_updates.append((user_id, is_active))


class FakeOwnerSearchStateStore:
    """Applies the same versioned-upsert semantics as the SQL adapter
    (ADR 0011 pattern), so worker-level tests can exercise duplicate and
    out-of-order Owner events without a real database."""

    def __init__(self) -> None:
        self._states: dict[uuid.UUID, OwnerSearchState] = {}

    async def get(self, user_id: uuid.UUID) -> OwnerSearchState | None:
        return self._states.get(user_id)

    async def upsert(self, state: OwnerSearchState) -> bool:
        existing = self._states.get(state.user_id)
        if existing is not None and existing.last_applied_outbox_id >= (
            state.last_applied_outbox_id
        ):
            return False
        self._states[state.user_id] = state
        return True


def _product_message(
    *, event_type: str, product_id: uuid.UUID, owner_id: uuid.UUID, revision: int = 4
) -> AbstractIncomingMessage:
    return cast(
        AbstractIncomingMessage,
        FakeMessage(
            event_type=event_type,
            payload={
                "product_id": str(product_id),
                "user_id": str(owner_id),
                "name": "Cordless drill",
                "description": "18V brushless drill",
                "category": "Tools",
                "price": 99.0,
                "is_active": True,
                "search_revision": revision,
            },
        ),
    )


def _owner_message(
    *, event_type: str, user_id: uuid.UUID, message_id: int
) -> AbstractIncomingMessage:
    return cast(
        AbstractIncomingMessage,
        FakeMessage(
            event_type=event_type,
            payload={"user_id": str(user_id)},
            message_id=str(message_id),
        ),
    )


@pytest.mark.asyncio
async def test_worker_indexes_a_complete_v2_product_snapshot() -> None:
    product_id = uuid.uuid4()
    owner_id = uuid.uuid4()
    indexer = RecordingIndexer()
    owner_states = FakeOwnerSearchStateStore()
    await owner_states.upsert(
        OwnerSearchState(user_id=owner_id, is_active=True, last_applied_outbox_id=1)
    )

    await handle_product_event(
        _product_message(
            event_type="product.deactivated.v2",
            product_id=product_id,
            owner_id=owner_id,
        ),
        indexer,
        owner_states,
    )

    [(snapshot, owner_is_active)] = indexer.snapshots
    assert snapshot == ProductSearchSnapshot(
        product_id=product_id,
        user_id=owner_id,
        name="Cordless drill",
        description="18V brushless drill",
        category="Tools",
        price=99.0,
        is_active=True,
        search_revision=4,
    )
    assert owner_is_active is True


@pytest.mark.asyncio
async def test_product_event_for_an_unknown_owner_indexes_as_owner_inactive() -> None:
    """Deny-by-default (issue #288 acceptance criterion 1): no Owner Search
    State row has ever been written for this owner."""
    indexer = RecordingIndexer()
    owner_states = FakeOwnerSearchStateStore()

    await handle_product_event(
        _product_message(
            event_type="product.created.v2",
            product_id=uuid.uuid4(),
            owner_id=uuid.uuid4(),
        ),
        indexer,
        owner_states,
    )

    [(_snapshot, owner_is_active)] = indexer.snapshots
    assert owner_is_active is False


@pytest.mark.asyncio
async def test_product_event_always_derives_owner_flag_from_local_state_not_event() -> (
    None
):
    """A delayed Product event must not resurrect a Product hidden by a since-
    deactivated owner (issue #288 acceptance criterion 3)."""
    owner_id = uuid.uuid4()
    indexer = RecordingIndexer()
    owner_states = FakeOwnerSearchStateStore()
    await owner_states.upsert(
        OwnerSearchState(user_id=owner_id, is_active=False, last_applied_outbox_id=9)
    )

    await handle_product_event(
        _product_message(
            event_type="product.updated.v2", product_id=uuid.uuid4(), owner_id=owner_id
        ),
        indexer,
        owner_states,
    )

    [(_snapshot, owner_is_active)] = indexer.snapshots
    assert owner_is_active is False


@pytest.mark.asyncio
async def test_owner_registered_seeds_active_state_without_needing_activation() -> None:
    """A brand-new owner is active but never gets an explicit
    `user.activated.v1` (that only fires on reactivation)."""
    user_id = uuid.uuid4()
    indexer = RecordingIndexer()
    owner_states = FakeOwnerSearchStateStore()

    await handle_owner_event(
        _owner_message(event_type="user.registered.v1", user_id=user_id, message_id=1),
        indexer,
        owner_states,
    )

    state = await owner_states.get(user_id)
    assert state is not None
    assert state.is_active is True
    assert indexer.owner_updates == [(user_id, True)]


@pytest.mark.parametrize(
    ("event_type", "expected_is_active"),
    [
        ("user.deactivated.v1", False),
        ("user.deleted.v1", False),
        ("user.activated.v1", True),
    ],
)
@pytest.mark.asyncio
async def test_owner_lifecycle_event_updates_state_and_mass_updates_index(
    event_type: str, expected_is_active: bool
) -> None:
    user_id = uuid.uuid4()
    indexer = RecordingIndexer()
    owner_states = FakeOwnerSearchStateStore()

    await handle_owner_event(
        _owner_message(event_type=event_type, user_id=user_id, message_id=10),
        indexer,
        owner_states,
    )

    state = await owner_states.get(user_id)
    assert state is not None
    assert state.is_active is expected_is_active
    assert indexer.owner_updates == [(user_id, expected_is_active)]


@pytest.mark.asyncio
async def test_duplicate_owner_event_does_not_reapply_the_mass_update() -> None:
    user_id = uuid.uuid4()
    indexer = RecordingIndexer()
    owner_states = FakeOwnerSearchStateStore()

    for _ in range(2):
        await handle_owner_event(
            _owner_message(
                event_type="user.deactivated.v1", user_id=user_id, message_id=7
            ),
            indexer,
            owner_states,
        )

    assert indexer.owner_updates == [(user_id, False)]


@pytest.mark.asyncio
async def test_out_of_order_owner_event_does_not_regress_state_or_reindex() -> None:
    """An older event arriving after a newer one must not re-hide a Product
    whose owner has already recovered (issue #288 acceptance criterion 5)."""
    user_id = uuid.uuid4()
    indexer = RecordingIndexer()
    owner_states = FakeOwnerSearchStateStore()

    await handle_owner_event(
        _owner_message(event_type="user.activated.v1", user_id=user_id, message_id=20),
        indexer,
        owner_states,
    )
    await handle_owner_event(
        _owner_message(
            event_type="user.deactivated.v1", user_id=user_id, message_id=15
        ),
        indexer,
        owner_states,
    )

    state = await owner_states.get(user_id)
    assert state is not None
    assert state.is_active is True
    assert indexer.owner_updates == [(user_id, True)]


@pytest.mark.asyncio
async def test_owner_deactivation_then_reactivation_recovers_visibility() -> None:
    user_id = uuid.uuid4()
    indexer = RecordingIndexer()
    owner_states = FakeOwnerSearchStateStore()

    await handle_owner_event(
        _owner_message(event_type="user.deactivated.v1", user_id=user_id, message_id=1),
        indexer,
        owner_states,
    )
    await handle_owner_event(
        _owner_message(event_type="user.activated.v1", user_id=user_id, message_id=2),
        indexer,
        owner_states,
    )

    assert indexer.owner_updates == [(user_id, False), (user_id, True)]


@pytest.mark.asyncio
async def test_dispatcher_routes_product_and_owner_events_to_the_right_handler() -> (
    None
):
    owner_id = uuid.uuid4()
    product_id = uuid.uuid4()
    indexer = RecordingIndexer()
    owner_states = FakeOwnerSearchStateStore()

    await handle_search_event(
        _owner_message(event_type="user.activated.v1", user_id=owner_id, message_id=1),
        indexer,
        owner_states,
    )
    await handle_search_event(
        _product_message(
            event_type="product.created.v2", product_id=product_id, owner_id=owner_id
        ),
        indexer,
        owner_states,
    )

    assert indexer.owner_updates == [(owner_id, True)]
    [(snapshot, owner_is_active)] = indexer.snapshots
    assert snapshot.product_id == product_id
    assert owner_is_active is True
