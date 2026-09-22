import uuid
from typing import Annotated

from fastapi import Header
from kernel_platform.security import Actor
from pydantic import BaseModel

from application.commands import (
    AuthorizePaymentCommand,
    CapturePaymentCommand,
    VoidPaymentCommand,
)
from application.queries import LookupPaymentQuery


class AuthorizePaymentRequest(BaseModel):
    amount: int
    payment_method_token: str

    def to_command(
        self, *, idempotency_key: str, actor: Actor
    ) -> AuthorizePaymentCommand:
        return AuthorizePaymentCommand(
            actor=actor,
            idempotency_key=idempotency_key,
            amount=self.amount,
            payment_method_token=self.payment_method_token,
        )


class VoidPaymentRequest:
    """Path- и header-bound."""

    def __init__(
        self,
        authorization_id: uuid.UUID,
        idempotency_key: Annotated[str, Header(alias="Idempotency-Key")],
    ) -> None:
        self.authorization_id = authorization_id
        self.idempotency_key = idempotency_key

    def to_command(self, *, actor: Actor) -> VoidPaymentCommand:
        return VoidPaymentCommand(
            actor=actor,
            authorization_id=self.authorization_id,
            idempotency_key=self.idempotency_key,
        )


class CapturePaymentRequest:
    """Path- и header-bound."""

    def __init__(
        self,
        authorization_id: uuid.UUID,
        idempotency_key: Annotated[str, Header(alias="Idempotency-Key")],
    ) -> None:
        self.authorization_id = authorization_id
        self.idempotency_key = idempotency_key

    def to_command(self, *, actor: Actor) -> CapturePaymentCommand:
        return CapturePaymentCommand(
            actor=actor,
            authorization_id=self.authorization_id,
            idempotency_key=self.idempotency_key,
        )


class LookupPaymentRequest(BaseModel):
    """Path-bound."""

    idempotency_key: str

    def to_query(self) -> LookupPaymentQuery:
        return LookupPaymentQuery(idempotency_key=self.idempotency_key)
