"""ADR 0033: shared framework-independent Actor/ActorRole contract."""

import dataclasses
import uuid

import pytest

from kernel_platform.security import Actor, ActorRole


def test_actor_role_values_match_the_pre_existing_service_role_strings() -> None:
    assert ActorRole.ADMIN.value == "admin"
    assert ActorRole.USER.value == "user"


def test_actor_is_frozen() -> None:
    actor = Actor(id=uuid.uuid4(), role=ActorRole.USER)

    with pytest.raises(dataclasses.FrozenInstanceError):
        actor.role = ActorRole.ADMIN  # type: ignore[misc]


def test_actor_carries_id_and_role() -> None:
    user_id = uuid.uuid4()

    actor = Actor(id=user_id, role=ActorRole.ADMIN)

    assert actor.id == user_id
    assert actor.role is ActorRole.ADMIN
