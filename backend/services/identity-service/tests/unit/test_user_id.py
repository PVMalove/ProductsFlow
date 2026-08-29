import uuid

from identity.domain.user_id import UserId


def test_user_ids_with_the_same_value_are_equal() -> None:
    value = uuid.uuid4()

    assert UserId(value) == UserId(value)


def test_user_ids_with_the_same_value_hash_the_same() -> None:
    value = uuid.uuid4()

    assert hash(UserId(value)) == hash(UserId(value))


def test_user_ids_with_different_values_are_not_equal() -> None:
    assert UserId(uuid.uuid4()) != UserId(uuid.uuid4())


def test_generate_returns_a_fresh_user_id_each_time() -> None:
    assert UserId.generate() != UserId.generate()


def test_a_user_id_is_not_equal_to_a_bare_uuid() -> None:
    value = uuid.uuid4()

    assert UserId(value) != value
