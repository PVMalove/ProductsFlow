class ApplicationError(Exception):
    """Base class for expected failures at the application boundary."""


class ProductNotFoundError(ApplicationError):
    """The requested product does not exist or is not visible."""


class ProductAccessDeniedError(ApplicationError):
    """The actor is not allowed to perform the requested product operation."""


class IdentityUnavailableError(ApplicationError):
    """The identity service could not answer an authorization query."""
