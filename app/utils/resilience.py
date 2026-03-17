import random
import time
from dataclasses import dataclass
from typing import Any, Callable, Optional, Sequence, Type, TypeVar

import requests

T = TypeVar("T")


@dataclass(frozen=True)
class RetryConfig:
    """Retry configuration for transient external-service failures."""

    max_attempts: int = 4
    base_delay_s: float = 0.25
    max_delay_s: float = 4.0
    jitter_s: float = 0.25


def _sleep_with_backoff(attempt: int, cfg: RetryConfig) -> None:
    exp = min(cfg.max_delay_s, cfg.base_delay_s * (2 ** max(0, attempt - 1)))
    jitter = random.uniform(0, cfg.jitter_s)
    time.sleep(exp + jitter)


def retry(
    *,
    cfg: RetryConfig = RetryConfig(),
    retry_on: Sequence[Type[BaseException]] = (
        requests.exceptions.Timeout,
        requests.exceptions.ConnectionError,
        requests.exceptions.HTTPError,
    ),
    is_retryable: Optional[Callable[[BaseException], bool]] = None,
) -> Callable[[Callable[..., T]], Callable[..., T]]:
    """Decorator implementing exponential backoff retries for sync callables."""

    def decorator(fn: Callable[..., T]) -> Callable[..., T]:
        def wrapped(*args: Any, **kwargs: Any) -> T:
            last_exc: Optional[BaseException] = None
            for attempt in range(1, max(1, cfg.max_attempts) + 1):
                try:
                    return fn(*args, **kwargs)
                except retry_on as exc:  # type: ignore[misc]
                    if is_retryable is not None and not is_retryable(exc):
                        raise
                    last_exc = exc
                    if attempt >= cfg.max_attempts:
                        raise
                    _sleep_with_backoff(attempt, cfg)
            assert last_exc is not None
            raise last_exc

        return wrapped

    return decorator


def is_retryable_http_error(exc: BaseException) -> bool:
    """Return True for HTTP errors that are commonly transient."""
    if not isinstance(exc, requests.exceptions.HTTPError):
        return True
    resp = getattr(exc, "response", None)
    if resp is None:
        return True
    return resp.status_code in {408, 429, 500, 502, 503, 504}

