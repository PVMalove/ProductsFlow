from application.errors import IdentityUnavailableError, ProductAccessDeniedError
from application.ports import Actor, IdentityGateway
from domain.product import Product


class ProductAuthorizer:
    """Application authorization rules shared by product use cases."""

    def __init__(self, identity: IdentityGateway) -> None:
        self._identity = identity

    async def is_admin(self, actor: Actor) -> bool:
        try:
            info = await self._identity.fetch_current_user(actor.token)
        except Exception as exc:
            raise IdentityUnavailableError from exc
        return info.role == "admin" and info.is_active

    async def require_owner_or_admin(self, actor: Actor, product: Product) -> None:
        if actor.user_id == product.user_id:
            return
        if await self.is_admin(actor):
            return
        raise ProductAccessDeniedError
