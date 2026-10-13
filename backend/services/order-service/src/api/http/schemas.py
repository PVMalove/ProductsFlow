import uuid
from typing import Annotated

from fastapi import Header
from kernel_platform.security import Actor
from pydantic import BaseModel

from application.commands import (
    AddCartLineCommand,
    CheckoutCommand,
    RemoveCartLineCommand,
    UpdateCartLineQuantityCommand,
)
from application.queries import GetCartQuery


class CheckoutRequest:
    """Header-bound."""

    def __init__(
        self,
        idempotency_key: Annotated[str, Header(alias="Idempotency-Key", min_length=1)],
    ) -> None:
        self.idempotency_key = idempotency_key

    def to_command(self, *, actor: Actor, bearer_token: str) -> CheckoutCommand:
        return CheckoutCommand(
            actor=actor,
            idempotency_key=self.idempotency_key,
            bearer_token=bearer_token,
        )


class GetCartRequest(BaseModel):
    """Без параметров (неявно использует ID пользователя)."""

    def to_query(self, *, actor: Actor) -> GetCartQuery:
        return GetCartQuery(user_id=actor.id)


class AddCartLineRequest(BaseModel):
    product_id: uuid.UUID
    # Валидация количества — доменная (`CartErrors.invalid_quantity`), не
    # Pydantic-уровня (мирует catalog's `ProductQuoteRequest`), поэтому здесь
    # нет `ge=1`.
    quantity: int

    def to_command(self, *, actor: Actor) -> AddCartLineCommand:
        return AddCartLineCommand(
            actor=actor, product_id=self.product_id, quantity=self.quantity
        )


class UpdateCartLineRequest(BaseModel):
    quantity: int

    def to_command(
        self, *, line_id: uuid.UUID, actor: Actor
    ) -> UpdateCartLineQuantityCommand:
        return UpdateCartLineQuantityCommand(
            actor=actor, line_id=line_id, quantity=self.quantity
        )


class RemoveCartLineRequest(BaseModel):
    """Path-bound."""

    line_id: uuid.UUID

    def to_command(self, *, actor: Actor) -> RemoveCartLineCommand:
        return RemoveCartLineCommand(actor=actor, line_id=self.line_id)
