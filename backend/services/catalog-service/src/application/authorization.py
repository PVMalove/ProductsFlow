# ruff: noqa: E501
from kernel_platform.security import ActorRole

from application.errors import ProductAccessDeniedError
from application.ports import Actor, IdentityGateway, IdentityUser
from domain.product import Product


class ProductAuthorizer:
    """Application authorization rules shared by product use cases."""

    def __init__(self, identity: IdentityGateway) -> None:
        self._identity = identity

    async def is_admin(self, actor: Actor) -> bool:
        info = await self._identity.fetch_current_user(actor.token)
        return info.role == ActorRole.ADMIN and info.is_active

    async def fetch_current_user(self, actor: Actor) -> IdentityUser:
        return await self._identity.fetch_current_user(actor.token)

    async def require_owner_or_admin(self, actor: Actor, product: Product) -> None:
        if actor.user_id == product.user_id:
            return
        if await self.is_admin(actor):
            return
        raise ProductAccessDeniedError
