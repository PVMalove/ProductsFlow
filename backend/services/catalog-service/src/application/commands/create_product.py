"""Create-product command and handler."""

from dataclasses import dataclass

from kernel_domain.result import Result

from application.ports import (
    Actor,
    IdentityGateway,
    OwnerReadModel,
    OwnerSnapshot,
    ProductCommandPort,
)
from domain.product import Product


@dataclass(frozen=True)
class CreateProductCommand:
    actor: Actor
    name: str
    description: str
    price: float
    category: str


class CreateProductCommandHandler:
    def __init__(
        self,
        repository: ProductCommandPort,
        owner_read_model: OwnerReadModel,
        identity: IdentityGateway,
    ) -> None:
        self._repository = repository
        self._owner_read_model = owner_read_model
        self._identity = identity

    async def handle(self, command: CreateProductCommand) -> Result[Product]:
        if await self._owner_read_model.get(command.actor.user_id) is None:
            info = await self._identity.fetch_current_user(command.actor.token)
            await self._owner_read_model.upsert(
                OwnerSnapshot(
                    user_id=info.id,
                    role=info.role,
                    is_active=info.is_active,
                    last_applied_outbox_id=0,
                )
            )
        return await self._repository.create(
            name=command.name,
            description=command.description,
            price=command.price,
            category=command.category,
            user_id=command.actor.user_id,
        )
