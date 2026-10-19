"""Thread-safe in-memory sliding-window rate limiter for sensitive endpoints.

Provides brute-force and abuse protection for account recovery and profile operations.
In a distributed production setup, this can be backed by Redis.
"""
import time
from collections import defaultdict
from threading import Lock
from typing import Dict, List, Tuple
from fastapi import HTTPException, Request, status


class SlidingWindowRateLimiter:
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
        return forwarded.split(",")[0].strip()
    return request.client.host if request.client else "unknown"
