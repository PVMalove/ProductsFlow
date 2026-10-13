"""Addressed, versioned commands transported through RabbitMQ."""

import json
import uuid
from collections.abc import Awaitable, Callable
from dataclasses import dataclass
from typing import Any, cast

from aio_pika import DeliveryMode, Message
from aio_pika.abc import (
    AbstractExchange,
    AbstractIncomingMessage,
    AbstractQueue,
    ConsumerTag,
    HeadersType,
)
from opentelemetry import trace
from opentelemetry.trace import SpanKind
from sqlalchemy.dialects.postgresql import insert
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from kernel_platform.consumer import consume
from kernel_platform.outbox.models import InboxMessage
from kernel_platform.outbox.trace_context import inject_trace_context, w3c_carrier


@dataclass(frozen=True, kw_only=True)
class Command:
    """A command envelope with identifiers needed for reliable processing."""

    command_id: uuid.UUID
    command_type: str
    causation_id: uuid.UUID
    correlation_id: str
    payload: dict[str, Any]

    def to_payload(self) -> dict[str, Any]:
        """Returns the stable JSON envelope sent to the command owner."""
        return {
            "command_id": str(self.command_id),
            "command_type": self.command_type,
            "causation_id": str(self.causation_id),
            "correlation_id": self.correlation_id,
            "payload": self.payload,
        }


CommandHandler = Callable[[AsyncSession, Command], Awaitable[None]]


def command_from_message(message: AbstractIncomingMessage) -> Command:
    """Validates and decodes the transport envelope into a command."""
    try:
        raw_payload = json.loads(message.body)
        if not isinstance(raw_payload, dict):
            raise ValueError("command body must be an object")
        command_id = uuid.UUID(raw_payload["command_id"])
        command_type = raw_payload["command_type"]
        correlation_id = raw_payload["correlation_id"]
        payload = raw_payload["payload"]
        causation_id_value = raw_payload["causation_id"]
    except (KeyError, TypeError, ValueError, json.JSONDecodeError) as error:
        raise ValueError("invalid command envelope") from error

    if (
        not isinstance(command_type, str)
        or not isinstance(correlation_id, str)
        or not isinstance(payload, dict)
        or not isinstance(causation_id_value, str)
    ):
        raise ValueError("invalid command envelope")
    if message.message_id != str(command_id) or message.type != command_type:
        raise ValueError("command AMQP properties do not match its envelope")

    try:
        causation_id = uuid.UUID(causation_id_value)
    except ValueError as error:
        raise ValueError("invalid command causation_id") from error
    return Command(
        command_id=command_id,
        command_type=command_type,
        causation_id=causation_id,
        correlation_id=correlation_id,
        payload=payload,
    )


def build_command_message(command: Command) -> Message:
    """Builds a persistent AMQP message carrying the active W3C context."""
    return Message(
        body=json.dumps(command.to_payload()).encode(),
        message_id=str(command.command_id),
        content_type="application/json",
        delivery_mode=DeliveryMode.PERSISTENT,
        type=command.command_type,
        headers=cast(HeadersType, inject_trace_context()),
    )


async def publish_command(
    exchange: AbstractExchange, command: Command, *, timeout_seconds: float
) -> object:
    """Publishes a command under a producer span to its exact routing key."""
    tracer = trace.get_tracer(__name__)
    with tracer.start_as_current_span("publish_command", kind=SpanKind.PRODUCER):
        return await exchange.publish(
            build_command_message(command),
            routing_key=command.command_type,
            mandatory=True,
            timeout=timeout_seconds,
        )


async def consume_command(
    queue: AbstractQueue,
    session_factory: async_sessionmaker[AsyncSession],
    handler: CommandHandler,
) -> ConsumerTag:
    """Consumes commands idempotently and commits inbox plus local effects.

    A successful insert into ``inbox_messages`` claims the command.  The
    handler receives exactly that transaction's session, so its business
    mutation and any outbox rows either commit with the inbox row or all roll
    back together.  A duplicate claim is a successful no-op and the shared
    AMQP consumer ACKs it.
    """

    async def handle(message: AbstractIncomingMessage) -> None:
        command = command_from_message(message)
        trace_carrier = w3c_carrier(dict(message.headers))
        async with session_factory() as session:
            async with session.begin():
                claimed_command_id = await session.scalar(
                    insert(InboxMessage)
                    .values(
                        command_id=command.command_id,
                        command_type=command.command_type,
                        causation_id=command.causation_id,
                        correlation_id=command.correlation_id,
                        trace_context=(
                            json.dumps(trace_carrier, separators=(",", ":"))
                            if trace_carrier
                            else None
                        ),
                    )
                    .on_conflict_do_nothing(index_elements=[InboxMessage.command_id])
                    .returning(InboxMessage.command_id)
                )
                if claimed_command_id is None:
                    return
                await handler(session, command)

    return await consume(queue, handle, prefetch_count=1)
