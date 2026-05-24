from collections import deque
from datetime import datetime, timedelta
from typing import Deque, Dict

from fastapi.responses import JSONResponse
from starlette.middleware.base import BaseHTTPMiddleware
from starlette.requests import Request
from starlette.responses import Response


class SlidingWindowCounter:
    """
    In-memory sliding window rate counter per key (typically IP address).

    Thread-safety note: uses deque with O(1) operations per request.
    For multi-process deployments, replace with a Redis-backed counter.
    """

    def __init__(self, limit: int, window_seconds: int) -> None:
        self.limit = limit
        self.window = timedelta(seconds=window_seconds)
        self._timestamps: Dict[str, Deque[datetime]] = {}

    def is_allowed(self, key: str) -> bool:
        """Return True if the request is within limits; False if rate-limited."""
        now = datetime.utcnow()
        window_start = now - self.window

        if key not in self._timestamps:
            self._timestamps[key] = deque()

        bucket = self._timestamps[key]

        # Evict timestamps outside the current window
        while bucket and bucket[0] < window_start:
            bucket.popleft()

        if len(bucket) >= self.limit:
            return False

        bucket.append(now)
        return True

    def request_count(self, key: str) -> int:
        """Return current request count in the window for a key."""
        now = datetime.utcnow()
        window_start = now - self.window
        bucket = self._timestamps.get(key, deque())
        return sum(1 for ts in bucket if ts >= window_start)


class RateLimiterMiddleware(BaseHTTPMiddleware):
    """
    Sliding-window rate limiter middleware.

    Default: 600 requests/min per IP — generous for normal use, blocks
    runaway automation. Adjust via constructor args for stricter endpoints.

    In tests, all requests arrive from "testclient" host, so the shared
    counter applies. Set limit high enough to not block the test suite.
    """

    def __init__(self, app, limit: int = 600, window_seconds: int = 60) -> None:
        super().__init__(app)
        self._counter = SlidingWindowCounter(limit=limit, window_seconds=window_seconds)

    async def dispatch(self, request: Request, call_next) -> Response:
        client_ip = request.client.host if request.client else "unknown"

        if not self._counter.is_allowed(client_ip):
            return JSONResponse(
                status_code=429,
                content={"detail": "Too many requests. Please slow down."},
            )

        return await call_next(request)
