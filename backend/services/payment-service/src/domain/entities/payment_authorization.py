import enum
import uuid
from datetime import UTC, datetime
from typing import cast

from kernel_domain import PRIVATE_MARKER
from kernel_domain.entity import Entity
from kernel_domain.result import Result

from domain.errors import PaymentErrors
from domain.psp_client import PspAuthorizeOutcome, PspCaptureOutcome

_MISSING = object()


class PaymentAuthorizationStatus(enum.StrEnum):
    AUTHORIZED = "authorized"
    DECLINED = "declined"
    AUTHORIZATION_UNKNOWN = "authorization_unknown"
    VOIDED = "voided"
    CAPTURED = "captured"
    CAPTURE_UNKNOWN = "capture_unknown"


_AUTHORIZE_STATUS_BY_OUTCOME: dict[PspAuthorizeOutcome, PaymentAuthorizationStatus] = {
    PspAuthorizeOutcome.SUCCESS: PaymentAuthorizationStatus.AUTHORIZED,
    PspAuthorizeOutcome.DECLINE: PaymentAuthorizationStatus.DECLINED,
    PspAuthorizeOutcome.TIMEOUT: PaymentAuthorizationStatus.AUTHORIZATION_UNKNOWN,
}

_CAPTURE_STATUS_BY_OUTCOME: dict[PspCaptureOutcome, PaymentAuthorizationStatus] = {
    PspCaptureOutcome.CAPTURED: PaymentAuthorizationStatus.CAPTURED,
    PspCaptureOutcome.UNKNOWN: PaymentAuthorizationStatus.CAPTURE_UNKNOWN,
}


class PaymentAuthorization(Entity[uuid.UUID]):
    """Агрегат авторизации платежа (ADR 0016, issue #368). PK = свежий
    `uuid.uuid4()` (не сам idempotency-ключ — произвольная клиентская строка,
    не заранее существующий системный GUID; ADR 0006 требует, чтобы
    идентификаторы агрегатов всегда были GUID). Никаких доменных событий
    сегодня (архитектурный бриф D1) — RabbitMQ/outbox-обвязка вне скоупа #368.

    Конструктор вызывается только через `create()` (новая авторизация) или
    `reconstitute()` (гидратация из БД)."""

    def __init__(
        self,
        marker: object = _MISSING,
        id: uuid.UUID = cast("uuid.UUID", _MISSING),
        *,
        idempotency_key: str,
        amount: int,
        payment_method_token: str,
        status: PaymentAuthorizationStatus,
        void_idempotency_key: str | None,
        capture_idempotency_key: str | None,
        created_at: datetime,
    ) -> None:
        super().__init__(marker, id=id)
        self.idempotency_key = idempotency_key
        self.amount = amount
        self.payment_method_token = payment_method_token
        self.status = status
        self.void_idempotency_key = void_idempotency_key
        self.capture_idempotency_key = capture_idempotency_key
        self.created_at = created_at

    @classmethod
    def create(
        cls,
        idempotency_key: str,
        amount: int,
        payment_method_token: str,
        outcome: PspAuthorizeOutcome,
    ) -> Result["PaymentAuthorization"]:
        if amount <= 0:
            return Result["PaymentAuthorization"].fail(PaymentErrors.invalid_amount())

        return Result["PaymentAuthorization"].ok(
            cls(
                PRIVATE_MARKER,
                uuid.uuid4(),
                idempotency_key=idempotency_key,
                amount=amount,
                payment_method_token=payment_method_token,
                status=_AUTHORIZE_STATUS_BY_OUTCOME[outcome],
                void_idempotency_key=None,
                capture_idempotency_key=None,
                created_at=datetime.now(UTC),
            )
        )

    @classmethod
    def reconstitute(
        cls,
        id: uuid.UUID,
        *,
        idempotency_key: str,
        amount: int,
        payment_method_token: str,
        status: PaymentAuthorizationStatus,
        void_idempotency_key: str | None,
        capture_idempotency_key: str | None,
        created_at: datetime,
    ) -> "PaymentAuthorization":
        return cls(
            PRIVATE_MARKER,
            id,
            idempotency_key=idempotency_key,
            amount=amount,
            payment_method_token=payment_method_token,
            status=status,
            void_idempotency_key=void_idempotency_key,
            capture_idempotency_key=capture_idempotency_key,
            created_at=created_at,
        )

    def void(self, idempotency_key: str) -> Result[None]:
        """Идемпотентный no-op при повторе тем же ключом; Test PSP не хранит
        внешнего состояния, которое нужно было бы отменять — вызова PSP не
        требуется вовсе (архитектурный бриф D4)."""
        if self.void_idempotency_key == idempotency_key:
            return Result[None].ok(None)
        if self.status is not PaymentAuthorizationStatus.AUTHORIZED:
            return Result[None].fail(PaymentErrors.invalid_authorization_state())

        self.void_idempotency_key = idempotency_key
        self.status = PaymentAuthorizationStatus.VOIDED
        return Result[None].ok(None)

    def capture(self, idempotency_key: str, outcome: PspCaptureOutcome) -> Result[None]:
        """Идемпотентный no-op при повторе тем же ключом. `CAPTURE_UNKNOWN` с
        другим ключом получает свой узнаваемый код — ADR 0016 запрещает
        повторять capture до сверки результата."""
        if self.capture_idempotency_key == idempotency_key:
            return Result[None].ok(None)
        if self.status is PaymentAuthorizationStatus.CAPTURE_UNKNOWN:
            return Result[None].fail(PaymentErrors.capture_pending_reconciliation())
        if self.status is not PaymentAuthorizationStatus.AUTHORIZED:
            return Result[None].fail(PaymentErrors.invalid_authorization_state())

        self.capture_idempotency_key = idempotency_key
        self.status = _CAPTURE_STATUS_BY_OUTCOME[outcome]
        return Result[None].ok(None)
