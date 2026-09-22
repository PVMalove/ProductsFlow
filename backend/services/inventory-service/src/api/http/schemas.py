import uuid

from kernel_platform.security import Actor
from pydantic import BaseModel

from application.commands import AdjustInventoryStockCommand


class InventoryAdjustmentRequest(BaseModel):
    delta: int
    reason: str

    def to_command(
        self, *, product_id: uuid.UUID, actor: Actor
    ) -> AdjustInventoryStockCommand:
        return AdjustInventoryStockCommand(
            actor=actor,
            product_id=product_id,
            delta=self.delta,
            reason=self.reason,
        )
