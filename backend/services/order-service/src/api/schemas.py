import uuid

from kernel_platform.security import Actor
from pydantic import BaseModel

from application.commands import (
    AddCartLineCommand,
    RemoveCartLineCommand,
    UpdateCartLineQuantityCommand,
)


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


def to_remove_command(*, line_id: uuid.UUID, actor: Actor) -> RemoveCartLineCommand:
    return RemoveCartLineCommand(actor=actor, line_id=line_id)
