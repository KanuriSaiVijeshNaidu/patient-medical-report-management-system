"""Sliding-window rate limiter for sensitive authentication and recovery endpoints.

Architecture & Concurrency Considerations:
- In Development:
  Uses an in-memory thread-safe sliding window with Python threading.Lock.
  This protects single-process instances (e.g. uvicorn --workers 1).
- In Production (Multi-Worker / Multi-Instance):
  An in-memory dictionary is per-process and does NOT share state across multiple
  Uvicorn/Gunicorn worker processes or horizontally scaled container instances/pods.
  Production deployments MUST use an external shared store such as Redis
  (via redis.asyncio or redis-py sliding window sorted set ZADD/ZREMRANGEBYSCORE)
  or edge-layer rate limiting (Cloudflare WAF / AWS WAF / API Gateway).
"""
import logging
import time
from collections import defaultdict
from threading import Lock
from typing import Dict, List, Tuple, Optional
from fastapi import HTTPException, Request, status

logger = logging.getLogger("security.rate_limit")


class SlidingWindowRateLimiter:
    """In-memory sliding window rate limiter suitable for single-process development."""

    def __init__(self):
        self._lock = Lock()
        # Key: (endpoint_key, identifier), Value: list of monotonic timestamps
        self._requests: Dict[Tuple[str, str], List[float]] = defaultdict(list)

    def check(
        self,
        key: str,
        identifier: str,
        max_requests: int,
        window_seconds: int,
    ) -> None:
        """Checks if a request exceeds rate limits within the sliding window.

        Raises HTTPException(429) if exceeded.
        """
        now = time.monotonic()
        bucket_key = (key, identifier)

        with self._lock:
            timestamps = self._requests[bucket_key]
            # Prune timestamps outside window
            cutoff = now - window_seconds
            self._requests[bucket_key] = [t for t in timestamps if t > cutoff]

            if len(self._requests[bucket_key]) >= max_requests:
                oldest = self._requests[bucket_key][0]
                retry_after = int(window_seconds - (now - oldest)) + 1
                logger.warning(
                    "Rate limit exceeded: key=%s identifier=%s count=%d max=%d retry_after=%ds",
                    key, identifier, len(self._requests[bucket_key]), max_requests, retry_after,
                    extra={
                        "event": "rate_limit_exceeded",
                        "rate_limit_key": key,
                        "client_identifier": identifier,
                        "retry_after_seconds": retry_after,
                        "outcome": "denied",
                    }
                )
                raise HTTPException(
                    status_code=status.HTTP_429_TOO_MANY_REQUESTS,
                    detail=f"Rate limit exceeded. Too many requests for {key}. Try again in {retry_after} seconds.",
                    headers={"Retry-After": str(retry_after)},
                )

            self._requests[bucket_key].append(now)

    def reset_for_tests(self):
        """Clears state for isolated test execution."""
        with self._lock:
            self._requests.clear()


rate_limiter = SlidingWindowRateLimiter()


def get_client_ip(request: Request) -> str:
    """Extracts client IP safely, considering X-Forwarded-For if behind a proxy."""
    forwarded = request.headers.get("x-forwarded-for")
    if forwarded:
        # First entry in X-Forwarded-For is client origin IP
        return forwarded.split(",")[0].strip()
    return request.client.host if request.client else "unknown"
