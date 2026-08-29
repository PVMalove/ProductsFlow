from datetime import timedelta

from kernel_platform.outbox.publisher import (
    BACKOFF_BASE_SECONDS,
    BACKOFF_CEILING_SECONDS,
    compute_backoff,
)


def test_compute_backoff_first_attempt_returns_base() -> None:
    assert compute_backoff(1) == timedelta(seconds=BACKOFF_BASE_SECONDS)


def test_compute_backoff_doubles_per_attempt() -> None:
    assert compute_backoff(2) == timedelta(seconds=BACKOFF_BASE_SECONDS * 2)
    assert compute_backoff(3) == timedelta(seconds=BACKOFF_BASE_SECONDS * 4)


def test_compute_backoff_caps_at_ceiling() -> None:
    assert compute_backoff(1000) == timedelta(seconds=BACKOFF_CEILING_SECONDS)


def test_compute_backoff_does_not_overflow_on_unbounded_attempts() -> None:
    # Publisher никогда не сдаётся (ADR 0014) — attempts растёт без верхней
    # границы при затяжном простое брокера; 2**(attempts - 1) не должен
    # переполнять float.
    assert compute_backoff(10_000_000) == timedelta(seconds=BACKOFF_CEILING_SECONDS)
