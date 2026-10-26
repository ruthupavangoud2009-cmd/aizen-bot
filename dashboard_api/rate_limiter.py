"""In-memory thread-safe rate limiter with sliding window tracking.

Protects Discord OAuth2 endpoints and settings modification routes
from abuse, credential-stuffing, and rapid flooding.
"""
from __future__ import annotations

import time
from collections import defaultdict
from typing import Dict, List


class SlidingWindowRateLimiter:
    """Sliding-window rate limiter per client IP or session key."""

    def __init__(self, default_limit: int = 60, window_seconds: int = 60) -> None:
        self.default_limit = default_limit
        self.window_seconds = window_seconds
        self._history: Dict[str, List[float]] = defaultdict(list)
        self._last_cleanup = time.time()

    def _cleanup_old_keys(self, now: float) -> None:
        """Periodic cleanup to prevent unbounded memory growth."""
        if now - self._last_cleanup < 300:  # every 5 minutes
            return
        self._last_cleanup = now
        expired_keys = []
        cutoff = now - self.window_seconds
        for key, timestamps in self._history.items():
            valid = [ts for ts in timestamps if ts > cutoff]
            if not valid:
                expired_keys.append(key)
            else:
                self._history[key] = valid
        for key in expired_keys:
            del self._history[key]

    def is_allowed(
        self,
        key: str,
        limit: int | None = None,
        window: int | None = None
    ) -> tuple[bool, int, float]:
        """Check if request for key is permitted under rate limit.

        Returns:
            (allowed: bool, remaining_requests: int, reset_in_seconds: float)
        """
        now = time.time()
        self._cleanup_old_keys(now)

        req_limit = limit if limit is not None else self.default_limit
        req_window = window if window is not None else self.window_seconds
        cutoff = now - req_window

        # Filter out timestamps outside the active window
        timestamps = [ts for ts in self._history[key] if ts > cutoff]

        if len(timestamps) >= req_limit:
            oldest = timestamps[0]
            reset_in = max(0.0, (oldest + req_window) - now)
            self._history[key] = timestamps
            return False, 0, reset_in

        timestamps.append(now)
        self._history[key] = timestamps
        remaining = req_limit - len(timestamps)
        reset_in = req_window
        return True, remaining, reset_in

    def reset(self) -> None:
        """Reset internal history (useful for test suites)."""
        self._history.clear()
        self._last_cleanup = time.time()
