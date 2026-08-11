from typing import Annotated

from fastapi import Path
from pydantic import BaseModel, ConfigDict, Field

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
