"""
In-memory sliding-window rate limiter with lockout.

Two singletons are exported:
  - voice_limiter  — for voice challenge failures
  - login_limiter  — for password login failures

For production, replace the in-memory backing store with Redis.
"""
from collections import defaultdict
from datetime import datetime, timedelta, timezone
from typing import Dict, List
from config import settings


def _now() -> datetime:
    return datetime.now(timezone.utc)


class RateLimiter:
    """
    Sliding-window rate limiter with automatic lockout.

    Parameters
    ----------
    max_attempts : int
        Maximum failures allowed within ``window_minutes``.
    window_minutes : int
        Rolling window used to count failures.
    lockout_minutes : int
        Duration of lockout after exceeding ``max_attempts``.
    """

    def __init__(self, max_attempts: int, window_minutes: int, lockout_minutes: int):
        self.max_attempts = max_attempts
        self.window = timedelta(minutes=window_minutes)
        self.lockout_duration = timedelta(minutes=lockout_minutes)
        self._attempts: Dict[str, List[datetime]] = defaultdict(list)
        self._lockouts: Dict[str, datetime] = {}

    # ── Public API ────────────────────────────────────────────────────────────

    def is_locked(self, identifier: str) -> bool:
        """Return ``True`` if the identifier is currently locked out."""
        if identifier in self._lockouts:
            if _now() < self._lockouts[identifier]:
                return True
            # Lock expired — clean up
            self._clear(identifier)
        return False

    def lockout_remaining_seconds(self, identifier: str) -> int:
        """Seconds remaining in active lockout; 0 if not locked."""
        if identifier in self._lockouts:
            remaining = (self._lockouts[identifier] - _now()).total_seconds()
            return max(0, int(remaining))
        return 0

    def record_failure(self, identifier: str) -> bool:
        """
        Record a failed attempt.

        Returns ``True`` if this failure triggered a new lockout.
        """
        self._prune(identifier)
        self._attempts[identifier].append(_now())
        if len(self._attempts[identifier]) >= self.max_attempts:
            self._lockouts[identifier] = _now() + self.lockout_duration
            self._attempts[identifier] = []
            return True  # lockout triggered
        return False

    def record_success(self, identifier: str) -> None:
        """Reset the failure counter after a successful attempt."""
        self._clear(identifier)

    def remaining_attempts(self, identifier: str) -> int:
        """How many more failures the identifier can make before lockout."""
        self._prune(identifier)
        return max(0, self.max_attempts - len(self._attempts[identifier]))

    # ── Internals ─────────────────────────────────────────────────────────────

    def _prune(self, identifier: str) -> None:
        """Remove attempts that have fallen outside the sliding window."""
        cutoff = _now() - self.window
        self._attempts[identifier] = [
            t for t in self._attempts[identifier] if t > cutoff
        ]

    def _clear(self, identifier: str) -> None:
        self._attempts.pop(identifier, None)
        self._lockouts.pop(identifier, None)


# ── Module-level singletons ───────────────────────────────────────────────────

voice_limiter = RateLimiter(
    max_attempts=settings.MAX_VOICE_ATTEMPTS,
    window_minutes=settings.VOICE_LOCKOUT_MINUTES,
    lockout_minutes=settings.VOICE_LOCKOUT_MINUTES,
)

login_limiter = RateLimiter(
    max_attempts=settings.MAX_LOGIN_ATTEMPTS,
    window_minutes=settings.LOGIN_LOCKOUT_MINUTES,
    lockout_minutes=settings.LOGIN_LOCKOUT_MINUTES,
)
