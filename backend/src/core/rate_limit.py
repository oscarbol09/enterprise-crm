"""
Distributed Sliding-Window Rate Limiting via Redis (with graceful in-memory fallback).
"""

import time
from collections import defaultdict, deque
from collections.abc import Callable

import structlog
from fastapi import HTTPException, Request, status
from redis.asyncio import Redis

from src.core.config import settings

logger = structlog.get_logger(__name__)

_redis_client: Redis | None = None
_memory_buckets: dict[str, deque[float]] = defaultdict(deque)


def get_redis_client() -> Redis | None:
    global _redis_client
    if _redis_client is None and settings.RATE_LIMIT_ENABLED and settings.REDIS_URL:
        _redis_client = Redis.from_url(settings.REDIS_URL, decode_responses=True)
    return _redis_client


def set_redis_client(client: Redis | None) -> None:
    """Allows injecting fakeredis or a custom Redis client during testing."""
    global _redis_client
    _redis_client = client


def reset_memory_rate_limits() -> None:
    _memory_buckets.clear()


async def _check_redis_window(client: Redis, key: str, limit: int, window_seconds: int) -> bool:
    now_ms = int(time.time() * 1000)
    window_start_ms = now_ms - (window_seconds * 1000)
    member = f"{now_ms}:{time.perf_counter_ns()}"

    pipe = client.pipeline()
    pipe.zremrangebyscore(key, 0, window_start_ms)
    pipe.zadd(key, {member: now_ms})
    pipe.zcard(key)
    pipe.expire(key, window_seconds + 1)
    _, _, count, _ = await pipe.execute()
    return int(count) <= limit


def _check_memory_window(key: str, limit: int, window_seconds: int) -> bool:
    now = time.monotonic()
    cutoff = now - window_seconds
    bucket = _memory_buckets[key]
    while bucket and bucket[0] < cutoff:
        bucket.popleft()
    bucket.append(now)
    return len(bucket) <= limit


def rate_limit(scope: str, limit: int, window_seconds: int = 60) -> Callable:
    """FastAPI dependency factory enforcing sliding-window limits per client IP and scope."""

    async def dependency(request: Request) -> None:
        if not settings.RATE_LIMIT_ENABLED:
            return

        client_ip = request.client.host if request.client else "unknown"
        key = f"rl:{scope}:{client_ip}"
        client = get_redis_client()

        allowed = True
        if client is not None:
            try:
                allowed = await _check_redis_window(client, key, limit, window_seconds)
            except Exception as exc:
                logger.warning("Redis rate limiter unavailable, falling back to local memory", error=str(exc))
                allowed = _check_memory_window(key, limit, window_seconds)
        else:
            allowed = _check_memory_window(key, limit, window_seconds)

        if not allowed:
            raise HTTPException(
                status_code=status.HTTP_429_TOO_MANY_REQUESTS,
                detail=f"Rate limit exceeded for {scope}. Retry after {window_seconds} seconds.",
                headers={"Retry-After": str(window_seconds)},
            )

    return dependency
