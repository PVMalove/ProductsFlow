import uuid

import pytest

from domain.value_objects.user_id import UserId


def test_user_ids_with_the_same_value_are_equal() -> None:
    value = uuid.uuid4()

    assert UserId.create(value) == UserId.create(value)


def test_user_ids_with_the_same_value_hash_the_same() -> None:
    value = uuid.uuid4()

    assert hash(UserId.create(value)) == hash(UserId.create(value))


def test_user_ids_with_different_values_are_not_equal() -> None:
    assert UserId.create(uuid.uuid4()) != UserId.create(uuid.uuid4())


def test_new_id_returns_a_fresh_user_id_each_time() -> None:
    assert UserId.new_id() != UserId.new_id()


def test_a_user_id_is_not_equal_to_a_bare_uuid() -> None:
    value = uuid.uuid4()

    assert UserId.create(value) != value


def test_direct_construction_raises_runtime_error() -> None:
    with pytest.raises(RuntimeError):
        UserId(uuid.uuid4())
