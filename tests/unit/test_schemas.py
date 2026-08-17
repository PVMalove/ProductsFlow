import pytest
from pydantic import ValidationError

from app.schemas import PasswordChange, UserCreate


def test_user_create_accepts_a_password_with_lowercase_letter_and_digit():
    user = UserCreate(username="alice", password="secret12")

    assert user.password == "secret12"


def test_user_create_rejects_a_password_shorter_than_eight_characters():
    with pytest.raises(ValidationError, match="минимум 8 символов"):
        UserCreate(username="alice", password="sec1")


def test_user_create_rejects_a_password_without_a_lowercase_letter():
    with pytest.raises(ValidationError, match="строчную букву"):
        UserCreate(username="alice", password="SECRET123")


def test_user_create_rejects_a_password_without_a_digit():
    with pytest.raises(ValidationError, match="цифру"):
        UserCreate(username="alice", password="secretpass")


def test_password_change_applies_the_same_rules_to_the_new_password():
    with pytest.raises(ValidationError, match="минимум 8 символов"):
        PasswordChange(old_password="whatever", new_password="sec1")
