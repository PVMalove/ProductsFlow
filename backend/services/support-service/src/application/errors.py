# ruff: noqa: E501
class TicketNotFoundError(LookupError):
    """Raised when a ticket is missing or hidden from an ordinary actor."""
