# ruff: noqa: E501
import json
import uuid

import aio_pika
import pytest
from aio_pika import ExchangeType
from aio_pika.abc import AbstractChannel

from kernel_platform.commands import Command, publish_command
from kernel_platform.outbox.settings import EVENTS_EXCHANGE_NAME
from kernel_platform.topology import (
    COMMANDS_EXCHANGE_NAME,
    DLX_EXCHANGE_NAME,
    RETRY_STAGE_TTL_MS,
    declare_command_topology,
    declare_topology,
)

# amqp_connection/channel (conftest.py) — module/session-scoped, привязаны к
# session-scoped event loop; тесты и фикстуры этого модуля должны идти на
# том же loop — см. identity-service's tests/integration/test_outbox_publisher.py.
# `declare_topology` теперь объявляет `productsflow.events` сам (issue #317),
# поэтому первый тест этого модуля неявно и проверяет создание с нуля, а
# `test_declare_topology_is_idempotent` — что повторное объявление безопасно.
pytestmark = pytest.mark.asyncio(loop_scope="session")

SERVICE_NAME = "kernel-topology-test"
MAIN_QUEUE_NAME = f"{SERVICE_NAME}.user-events"
DLQ_NAME = f"{MAIN_QUEUE_NAME}.dlq"


async def test_declare_topology_creates_dlx_main_queue_retry_stages_and_dlq(
    channel: AbstractChannel,
) -> None:
    await declare_topology(channel, SERVICE_NAME)

    # Редекларация с теми же type/durable/arguments проходит без исключения,
    # только если брокер реально хранит именно эти параметры — расхождение
    # бросило бы 406 PRECONDITION_FAILED. Так проверяются "типы/аргументы"
    # объявленных объектов без обращения к management API.
    await channel.declare_exchange(DLX_EXCHANGE_NAME, ExchangeType.DIRECT, durable=True)
    await channel.declare_queue(
        MAIN_QUEUE_NAME,
        durable=True,
        arguments={
            "x-queue-type": "quorum",
            "x-dead-letter-exchange": DLX_EXCHANGE_NAME,
            "x-dead-letter-routing-key": MAIN_QUEUE_NAME,
        },
    )
    for suffix, ttl_ms in RETRY_STAGE_TTL_MS.items():
        await channel.declare_queue(
            f"{MAIN_QUEUE_NAME}.{suffix}",
            durable=True,
            arguments={
                "x-dead-letter-exchange": "",
                "x-dead-letter-routing-key": MAIN_QUEUE_NAME,
                "x-message-ttl": ttl_ms,
            },
        )
    await channel.declare_queue(DLQ_NAME, durable=True)


async def test_declare_topology_is_idempotent(channel: AbstractChannel) -> None:
    await declare_topology(channel, SERVICE_NAME)

    # Повторный вызов с теми же параметрами (например, рестарт процесса) не
    # должен бросить PRECONDITION_FAILED и не должен создать дублей.
    await declare_topology(channel, SERVICE_NAME)


async def test_main_queue_receives_event_matching_wildcard_binding(
    channel: AbstractChannel,
) -> None:
    main_queue = await declare_topology(channel, SERVICE_NAME)
    events_exchange = await channel.get_exchange(EVENTS_EXCHANGE_NAME)

    confirmation = await events_exchange.publish(
        aio_pika.Message(body=b'{"user_id": 1}'),
        routing_key="user.registered.v1",
    )
    assert confirmation is not None

    incoming = await main_queue.get(fail=True)
    await incoming.ack()

    assert incoming.body == b'{"user_id": 1}'


async def test_command_topology_routes_a_versioned_command_to_its_only_owner(
    channel: AbstractChannel,
) -> None:
    """A command is delivered only through its owner's durable queue."""
    command_type = f"inventory.reserve.topology.{uuid.uuid4().hex}.v1"
    queue = await declare_command_topology(channel, command_type)
    command_queue_name = "commands.inventory.reserve.v1"
    commands_exchange = await channel.get_exchange(COMMANDS_EXCHANGE_NAME)
    await channel.declare_queue(
        command_queue_name,
        durable=True,
        arguments={
            "x-queue-type": "quorum",
            "x-dead-letter-exchange": DLX_EXCHANGE_NAME,
            "x-dead-letter-routing-key": command_queue_name,
        },
    )
    for suffix, ttl_ms in RETRY_STAGE_TTL_MS.items():
        await channel.declare_queue(
            f"{command_queue_name}.{suffix}",
            durable=True,
            arguments={
                "x-dead-letter-exchange": "",
                "x-dead-letter-routing-key": command_queue_name,
                "x-message-ttl": ttl_ms,
            },
        )
    command_dlq = await channel.declare_queue(f"{command_queue_name}.dlq", durable=True)
    command_dlx = await channel.get_exchange(DLX_EXCHANGE_NAME)
    await command_dlq.bind(command_dlx, routing_key=command_queue_name)
    command = Command(
        command_id=uuid.uuid4(),
        command_type=command_type,
        causation_id=uuid.uuid4(),
        correlation_id="checkout-42",
        payload={"order_id": "order-42"},
    )

    confirmation = await publish_command(
        commands_exchange, command, timeout_seconds=5.0
    )
    assert confirmation is not None

    incoming = await queue.get(fail=True)
    await incoming.ack()

    assert incoming.message_id == str(command.command_id)
    assert incoming.type == command_type
    assert json.loads(incoming.body) == {
        "command_id": str(command.command_id),
        "command_type": command_type,
        "causation_id": str(command.causation_id),
        "correlation_id": "checkout-42",
        "payload": {"order_id": "order-42"},
    }


async def test_command_topology_reuses_one_queue_for_the_same_command_type(
    channel: AbstractChannel,
) -> None:
    command_type = "payment.authorize.v1"

    first_owner_queue = await declare_command_topology(channel, command_type)
    second_owner_queue = await declare_command_topology(channel, command_type)

    assert first_owner_queue.name == "commands.payment.authorize.v1"
    assert second_owner_queue.name == first_owner_queue.name
