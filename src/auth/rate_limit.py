"""Simple in-memory rate limiter for future auth endpoints."""
import time
from collections import defaultdict


class RateLimiter:
    """Token bucket rate limiter.

    Tracks request counts per key (e.g., IP address or user ID)
    within a sliding time window.

    Usage:
        limiter = RateLimiter(max_requests=5, window_seconds=60)
        if not limiter.allow("user-123"):
            raise TooManyRequestsError()
    """

    def __init__(self, max_requests: int = 10, window_seconds: int = 60):
        self.max_requests = max_requests
        self.window_seconds = window_seconds
        self._requests: dict[str, list[float]] = defaultdict(list)

    def allow(self, key: str) -> bool:
        """Check if a request is allowed for the given key.

        Returns True if under the rate limit, False otherwise.
        """
        now = time.monotonic()
        cutoff = now - self.window_seconds

        # Remove expired entries
        self._requests[key] = [t for t in self._requests[key] if t > cutoff]

        if len(self._requests[key]) >= self.max_requests:
            return False

        self._requests[key].append(now)
        return True

    def reset(self, key: str) -> None:
        """Reset the rate limit for a specific key."""
        self._requests.pop(key, None)

    def remaining(self, key: str) -> int:
        """Get remaining requests allowed for a key."""
        now = time.monotonic()
        cutoff = now - self.window_seconds
        self._requests[key] = [t for t in self._requests[key] if t > cutoff]
        return max(0, self.max_requests - len(self._requests[key]))
