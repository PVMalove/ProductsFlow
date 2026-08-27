from datetime import datetime
from typing import Annotated, Literal

from fastapi import Path
from pydantic import BaseModel, ConfigDict, Field, field_validator
from pydantic_core import PydanticCustomError

from app.models import ProductAuditAction, UserAuditAction, UserRole

ProductId = Annotated[int, Path(gt=0)]
UserId = Annotated[int, Path(gt=0)]
ProductAuditSortField = Literal["created_at", "action", "actor_user_id", "product_id"]


class ProductBase(BaseModel):
    name: str = Field(min_length=3, max_length=100, description="Название продукта")
    category: str = Field(
        min_length=3, max_length=100, description="Категория продукта"
    )
    price: float = Field(..., ge=0, description="Цена продукта")
    description: str = ""
    is_featured: bool = False


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
    description: str | None = Field(default=None, description="Описание продукта")

    @field_validator("name", "category", "price", "description")
    @classmethod
    def _reject_explicit_null(cls, value: str | float | None) -> str | float | None:
        # В БД эти поля NOT NULL. Отсутствие поля в запросе (unset) сюда не
        # попадает — валидаторы по умолчанию не запускаются на default-значениях,
        # так что "не менять" по-прежнему работает. А явный null должен упасть
        # тут 422-м, а не долететь до IntegrityError и стать невнятным 409.
        if value is None:
            raise PydanticCustomError(
                "null_not_allowed", "это поле нельзя явно сбросить в null"
            )
        return value

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
    is_active: bool
    created_at: datetime


class FeaturedProduct(ProductResponse):
    image_url: str | None = None


class ProductImageRecord(BaseModel):
    """Валидированная из ORM запись картинки товара — то, что читает
    репозиторий; из неё роутер строит публичную ссылку (ProductImageResponse)."""

    model_config = ConfigDict(from_attributes=True)
    s3_key: str
    updated_at: datetime


class ProductImageResponse(BaseModel):
    image_url: str
    updated_at: datetime


class PageInfo(BaseModel):
    next_cursor: str | None
    prev_cursor: str | None
    has_more: bool
    has_prev: bool


class ProductListResponse(BaseModel):
    items: list[ProductResponse]
    page_info: PageInfo


class UserBase(BaseModel):
    username: str = Field(min_length=3, max_length=10)


class UserCreate(UserBase):
    password: str

    @field_validator("password")
    @classmethod
    def validate_password(cls, value: str) -> str:
        return _validate_password(value)


class UserResponse(UserBase):
    model_config = ConfigDict(from_attributes=True)
    id: int
    role: UserRole
    is_active: bool
    created_at: datetime
    updated_at: datetime


class TokenResponse(BaseModel):
    access_token: str
    token_type: str = "bearer"


class PasswordChange(BaseModel):
    old_password: str
    new_password: str

    @field_validator("new_password")
    @classmethod
    def validate_password(cls, value: str) -> str:
        return _validate_password(value)


class UserAuditLogResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)
    id: int
    user_id: int
    actor_user_id: int
    action: UserAuditAction
    description: str
    created_at: datetime


class ProductAuditLogResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)
    id: int
    product_id: int
    actor_user_id: int
    action: ProductAuditAction
    description: str
    created_at: datetime


class ProductAuditLogPage(BaseModel):
    items: list[ProductAuditLogResponse]
    page_index: int
    page_size: int
    total: int
    total_pages: int


def _validate_password(value: str) -> str:
    if len(value) < 8:
        raise ValueError("Пароль должен содержать минимум 8 символов")
    if not any(ch.islower() for ch in value):
        raise ValueError("Пароль должен содержать строчную букву")
    if not any(ch.isdigit() for ch in value):
        raise ValueError("Пароль должен содержать цифру")
    return value
