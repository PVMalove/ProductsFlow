import datetime

import pytest
from pydantic import ValidationError

from app.schemas import PasswordChange, ProductResponse, UserCreate


@pytest.fixture
def sample_product() -> ProductResponse:
    return ProductResponse(
        id=1,
        name="Чайник",
        category="Техника",
        price=2990.0,
        description="Электрический чайник",
        user_id=1,
        is_active=True,
        created_at=datetime.datetime.now(),
    )


def test_product_keeps_field_values(sample_product: ProductResponse):
    assert sample_product.id == 1
    assert sample_product.name == "Чайник"
    assert isinstance(sample_product.price, float)


def test_product_dump_to_dict_contains_all_fields(sample_product: ProductResponse):
    data = sample_product.model_dump()
    assert data["name"] == "Чайник"
    assert data["category"] == "Техника"
    assert data["price"] == 2990.0
    assert data["user_id"] == 1


def test_product_rejects_short_name():
    with pytest.raises(ValueError):
        ProductResponse(
            id=1,
            name="ab",  # короче min_length=3
            category="Бытовая техника",
            price=2990.0,
            description="",
            user_id=1,
            created_at=datetime.datetime.now(),
        )


def test_product_rejects_negative_price():
    with pytest.raises(ValueError):
        ProductResponse(
            id=1,
            name="Чайник",
            category="Бытовая техника",
            price=-100.0,  # ge=0
            description="",
            user_id=1,
            created_at=datetime.datetime.now(),
        )


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
