"""
Simple in-process circuit breaker.

States:
  CLOSED   — normal operation, requests pass through
  OPEN     — too many failures, requests rejected immediately (fast-fail)
  HALF_OPEN — cooldown elapsed, one probe request allowed through to test recovery

Usage:
    cb = CircuitBreaker("coingecko", failure_threshold=5, recovery_timeout=30)

    async with cb:
        result = await coingecko_client.fetch(...)
"""

import asyncio
import time
from enum import Enum

from app.core.exceptions import CircuitOpenError, NotFoundError
from app.core.logging import get_logger
from app.core.metrics import Gauge

logger = get_logger(__name__)

_circuit_state = Gauge(
    "crypto_circuit_breaker_state",
    "Circuit breaker state: 0=closed, 1=half_open, 2=open",
    ["service"],
)


class State(Enum):
    CLOSED = "closed"
    OPEN = "open"
    HALF_OPEN = "half_open"


class CircuitBreaker:
    def __init__(
        self,
        service: str,
        failure_threshold: int = 5,
        recovery_timeout: float = 30.0,
        ignored_exceptions: tuple[type[BaseException], ...] = (),
    ) -> None:
        self.service = service
        self.failure_threshold = failure_threshold
        self.recovery_timeout = recovery_timeout
        # Exceptions that represent a client-side condition (e.g. a 404 for a
        # coin that doesn't exist), not a provider outage. These must not count
        # as failures, otherwise repeated 404s would trip the breaker and block
        # all traffic to a healthy upstream.
        self.ignored_exceptions = ignored_exceptions

        self._state = State.CLOSED
        self._failure_count = 0
        self._last_failure_time: float = 0.0
        self._lock = asyncio.Lock()

    @property
    def state(self) -> State:
        return self._state

    def _record_success(self) -> None:
        self._failure_count = 0
        if self._state != State.CLOSED:
            logger.info("circuit_breaker_closed", service=self.service)
        self._state = State.CLOSED
        _circuit_state.labels(service=self.service).set(0)

    def _record_failure(self) -> None:
        self._failure_count += 1
        self._last_failure_time = time.monotonic()
        if self._failure_count >= self.failure_threshold:
            if self._state != State.OPEN:
                logger.warning(
                    "circuit_breaker_opened",
                    service=self.service,
                    failures=self._failure_count,
                )
            self._state = State.OPEN
            _circuit_state.labels(service=self.service).set(2)

    def _should_attempt_reset(self) -> bool:
        return (
            self._state == State.OPEN
            and time.monotonic() - self._last_failure_time >= self.recovery_timeout
        )

    async def __aenter__(self) -> "CircuitBreaker":
        async with self._lock:
            if self._should_attempt_reset():
                self._state = State.HALF_OPEN
                _circuit_state.labels(service=self.service).set(1)
                logger.info("circuit_breaker_half_open", service=self.service)

            if self._state == State.OPEN:
                raise CircuitOpenError(self.service)

        return self

    async def __aexit__(self, exc_type: type | None, exc: BaseException | None, tb: object) -> bool:
        async with self._lock:
            if exc_type is None:
                self._record_success()
            elif exc_type is not None and issubclass(exc_type, self.ignored_exceptions):
                # Client-side condition (e.g. 404) — neither a failure nor a
                # health signal. Leave the breaker state untouched.
                pass
            else:
                self._record_failure()
        return False  # never suppress the exception — let caller handle it


# Singletons — one breaker per external dependency.
# A 404 from CoinGecko (unknown coin) is a client-side condition, not an outage,
# so it must not count toward opening the breaker.
coingecko_breaker = CircuitBreaker(
    "coingecko",
    failure_threshold=5,
    recovery_timeout=30,
    ignored_exceptions=(NotFoundError,),
)
claude_breaker = CircuitBreaker("claude", failure_threshold=3, recovery_timeout=60)
