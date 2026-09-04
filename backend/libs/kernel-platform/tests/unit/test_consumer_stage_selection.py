# ruff: noqa: E501
from aio_pika.abc import HeadersType

from kernel_platform.consumer import next_stage_index

STAGE_QUEUE_NAMES = (
    "svc.user-events.retry.5s",
    "svc.user-events.retry.30s",
    "svc.user-events.retry.2m",
)


def test_next_stage_index_is_zero_without_x_death() -> None:
    assert next_stage_index({}, STAGE_QUEUE_NAMES) == 0


def test_next_stage_index_advances_past_last_matched_stage() -> None:
    headers: HeadersType = {
        "x-death": [
            {"queue": "svc.user-events.retry.5s", "reason": "expired", "count": 1}
        ]
    }
    assert next_stage_index(headers, STAGE_QUEUE_NAMES) == 1


def test_next_stage_index_saturates_after_last_stage() -> None:
    headers: HeadersType = {
        "x-death": [
            {"queue": "svc.user-events.retry.2m", "reason": "expired", "count": 1}
        ]
    }
    assert next_stage_index(headers, STAGE_QUEUE_NAMES) == 3


def test_next_stage_index_ignores_entries_from_other_queues() -> None:
    # Одна `x-death` запись — от чужой очереди/сервиса (например,
    # `catalog.user-events.retry.30s`, если бы оказалась в том же
    # заголовке); своих ступеней в ней нет — считаем, что попыток ещё не
    # было (issue #110, AC "не путает с x-death от чужих очередей").
    headers: HeadersType = {
        "x-death": [
            {
                "queue": "catalog.user-events.retry.30s",
                "reason": "expired",
                "count": 5,
            }
        ]
    }
    assert next_stage_index(headers, STAGE_QUEUE_NAMES) == 0


def test_next_stage_index_uses_own_entry_and_ignores_foreign_one() -> None:
    headers: HeadersType = {
        "x-death": [
            {"queue": "svc.user-events.retry.5s", "reason": "expired", "count": 1},
            {
                "queue": "catalog.user-events.retry.2m",
                "reason": "expired",
                "count": 9,
            },
        ]
    }
    assert next_stage_index(headers, STAGE_QUEUE_NAMES) == 1
