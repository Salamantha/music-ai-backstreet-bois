"""Token bucket, driven by an injected clock so tests do not sleep."""

from __future__ import annotations

import pytest

from chordcat.adapters.ratelimit import TokenBucket


def bucket(now, capacity=8, period=10.0):
    async def sleep(d):
        now[0] += d
    return TokenBucket(capacity, period, clock=lambda: now[0], sleep=sleep)


async def test_capacity_is_enforced_over_the_window():
    now = [0.0]
    b = bucket(now)
    for _ in range(8):
        await b.acquire()
    assert now[0] == 0.0, "the first full window should not wait"
    await b.acquire()
    assert now[0] >= 10.0


async def test_twenty_requests_span_at_least_two_windows():
    now = [0.0]
    b = bucket(now)
    for _ in range(20):
        await b.acquire()
    assert now[0] >= 10.0


async def test_observe_respects_a_server_side_stall():
    now = [0.0]
    b = bucket(now)
    b.observe({"X-Rate-Limit-Remaining": "0", "X-Rate-Limit-Reset": "7"})
    await b.acquire()
    assert now[0] >= 7.0


async def test_observe_lowers_capacity_from_the_server_limit():
    b = bucket([0.0], capacity=20)
    b.observe({"X-Rate-Limit-Limit": "10"})
    assert b.capacity <= 8


def test_penalize_returns_a_backoff_and_blocks():
    now = [0.0]
    b = bucket(now)
    delay = b.penalize(None, attempt=2)
    assert delay >= 4.0


def test_malformed_headers_are_ignored():
    b = bucket([0.0])
    b.observe({"X-Rate-Limit-Remaining": "not-a-number", "X-Rate-Limit-Reset": ""})
