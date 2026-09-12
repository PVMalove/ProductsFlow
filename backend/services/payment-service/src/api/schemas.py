import uuid

from kernel_platform.security import Actor
from pydantic import BaseModel

from application.commands import (
    AuthorizePaymentCommand,
    CapturePaymentCommand,
    VoidPaymentCommand,
)


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


def to_void_command(
    *, authorization_id: uuid.UUID, idempotency_key: str, actor: Actor
) -> VoidPaymentCommand:
    return VoidPaymentCommand(
        actor=actor, authorization_id=authorization_id, idempotency_key=idempotency_key
    )


def to_capture_command(
    *, authorization_id: uuid.UUID, idempotency_key: str, actor: Actor
) -> CapturePaymentCommand:
    return CapturePaymentCommand(
        actor=actor, authorization_id=authorization_id, idempotency_key=idempotency_key
    )
