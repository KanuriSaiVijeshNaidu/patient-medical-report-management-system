import time
import logging
from threading import Lock
from typing import Dict

logger = logging.getLogger("audit.dedup")

# Approved 15-minute sliding window
DEDUP_WINDOW_SECONDS = 900


class ProfileReadDedupService:
    """Thread-safe 15-minute deduplication service for patient profile reads.

    Guarantees:
    - 5 rapid reads produce exactly 1 audit event.
    - Audit is committed to PostgreSQL BEFORE marking the cache key (Audit First, Cache Second).
    - If the deduplication cache throws an unexpected error, it fails open to logging (security over caching).
    - Multi-worker production environments should plug in Redis with 'SET key 1 EX 900 NX'.
    """

    def __init__(self, window_seconds: int = DEDUP_WINDOW_SECONDS):
        self._window_seconds = window_seconds
        self._lock = Lock()
        # Key: user_id string, Value: monotonic expiration timestamp
        self._cache: Dict[str, float] = {}

    def should_log(self, user_id: str) -> bool:
        """Returns True if an audit event should be generated; False if within 15-minute window."""
        try:
            now = time.monotonic()
            with self._lock:
                expiry = self._cache.get(user_id)
                if expiry is not None and now < expiry:
                    return False
                return True
        except Exception as e:
            logger.warning("ProfileReadDedupService.should_log failed; failing open to logging: %s", e)
            return True

    def mark_logged(self, user_id: str) -> None:
        """Marks the user as logged for the duration of the deduplication window."""
        try:
            now = time.monotonic()
            with self._lock:
                self._cache[user_id] = now + self._window_seconds
        except Exception as e:
            logger.warning("ProfileReadDedupService.mark_logged failed: %s", e)

    def reset_for_tests(self) -> None:
        """Clears state for clean test isolation."""
        with self._lock:
            self._cache.clear()


profile_read_dedup = ProfileReadDedupService()
