"""Token bucket unit tests. A fake clock stands in for time: nothing sleeps."""

import pytest

from app.api.error_handlers import status_for
from app.errors import RateLimited
from app.rate_limit import TokenBucket


class FakeClock:
    def __init__(self) -> None:
        self.now = 1000.0

    def __call__(self) -> float:
        return self.now


def _bucket(capacity: int = 3, per_minute: float = 12) -> tuple[TokenBucket, FakeClock]:
    clock = FakeClock()
    return TokenBucket(capacity, per_minute / 60, clock=clock), clock


def test_a_full_bucket_allows_a_burst_up_to_its_capacity_then_rejects():
    bucket, _ = _bucket(capacity=3)
    for _ in range(3):
        bucket.take()
    with pytest.raises(RateLimited):
        bucket.take()


def test_the_rejection_says_how_long_until_the_next_token():
    bucket, clock = _bucket(capacity=1, per_minute=12)  # one token every 5 s
    bucket.take()
    with pytest.raises(RateLimited) as rejected:
        bucket.take()
    assert rejected.value.retry_after_seconds == pytest.approx(5.0)

    clock.now += 2.0
    with pytest.raises(RateLimited) as rejected:
        bucket.take()
    assert rejected.value.retry_after_seconds == pytest.approx(3.0)


def test_tokens_come_back_at_the_refill_rate():
    bucket, clock = _bucket(capacity=3, per_minute=12)
    for _ in range(3):
        bucket.take()

    clock.now += 4.9
    with pytest.raises(RateLimited):
        bucket.take()
    clock.now += 0.2  # 5.1 s since empty: exactly one token has accrued
    bucket.take()
    with pytest.raises(RateLimited):
        bucket.take()


def test_a_rejected_request_does_not_push_the_next_token_further_away():
    # Hammering an empty bucket must not starve it (a classic bug: resetting the timer on reject).
    bucket, clock = _bucket(capacity=1, per_minute=12)
    bucket.take()
    for _ in range(50):
        clock.now += 0.1  # 50 rejected attempts over 5 s
        try:
            bucket.take()
        except RateLimited:
            continue
        break
    else:
        pytest.fail("no token after 5 s of continuous attempts")


def test_an_idle_bucket_never_holds_more_than_its_capacity():
    bucket, clock = _bucket(capacity=3)
    clock.now += 3600  # an hour idle
    for _ in range(3):
        bucket.take()
    with pytest.raises(RateLimited):
        bucket.take()


def test_sustained_traffic_at_the_refill_rate_is_never_rejected():
    bucket, clock = _bucket(capacity=6, per_minute=12)
    for _ in range(100):
        bucket.take()
        clock.now += 5.0


@pytest.mark.parametrize(("capacity", "rate"), [(0, 1.0), (3, 0.0), (3, -1.0)])
def test_nonsense_settings_are_refused_at_startup(capacity, rate):
    with pytest.raises(ValueError):
        TokenBucket(capacity, rate)


def test_rate_limited_maps_to_429():
    assert status_for(RateLimited("slow down", 2.0)) == 429
