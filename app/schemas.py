from datetime import datetime
from typing import Annotated

from fastapi import Path
from pydantic import BaseModel, ConfigDict, Field, field_validator

from app.models import UserRole

ProductID = Annotated[int, Path(gt=0)]


class ProductBase(BaseModel):
    name: str = Field(min_length=3, max_length=100, description="Название продукта")
    category: str = Field(
        min_length=3, max_length=100, description="Категория продукта"
    )
    price: float = Field(..., ge=0, description="Цена продукта")
    description: str = ""


class ProductCreate(ProductBase):
    model_config = ConfigDict(
        json_schema_extra={
            "examples": [
                {
                    "name": "Название товара",
                    "category": "Категория",
                    "price": 0.0,
                    "description": "Описание товара",
                }
            ]
        }
    )


class ProductUpdate(BaseModel):
    name: str | None = Field(
        default=None, min_length=3, max_length=100, description="Название продукта"
    )
    category: str | None = Field(
        default=None, min_length=3, max_length=100, description="Категория продукта"
    )
    price: float | None = Field(default=None, ge=0, description="Цена продукта")
    description: str = ""
    model_config = ConfigDict(
        json_schema_extra={
            "examples": [
                {
                    "name": "Название товара",
                    "category": "Категория",
                    "price": 0.0,
                    "description": "Описание товара",
                }
            ]
        }
    )


class ProductResponse(ProductBase):
    model_config = ConfigDict(from_attributes=True)
    id: int
    user_id: int


class UserBase(BaseModel):
    username: str = Field(min_length=3, max_length=10)


class UserCreate(UserBase):
    password: str

    @field_validator("password")
    @classmethod
    def validate_password(cls, value: str) -> str:
        if len(value) < 8:
            raise ValueError("Пароль должен содержать минимум 8 символов")
        if not any(ch.islower() for ch in value):
            raise ValueError("Пароль должен содержать строчную букву")
        if not any(ch.isdigit() for ch in value):
            raise ValueError("Пароль должен содержать цифру")
        return value


class UserResponse(UserBase):
    model_config = ConfigDict(from_attributes=True)
    id: int
    role: UserRole
    is_active: bool
    create_at: datetime
    updated_at: datetime
