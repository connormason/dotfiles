"""
Retry decorator with exponential backoff
"""
from __future__ import annotations

import time
from functools import wraps
from typing import TYPE_CHECKING
from typing import Any
from typing import Callable

from cli.utils.styling import printf

if TYPE_CHECKING:

    from cli.infra.types import F

__all__ = [
    'retry_on_failure',
]


# ==================================================================================================
# Decorators
# ==================================================================================================


def retry_on_failure(
    *,
    max_attempts: int = 3,
    delay: float = 2.0,
    backoff: float = 2.0,
) -> Callable[[F], F]:
    """
    Decorator to retry failed operations with exponential backoff

    :param max_attempts: maximum number of retry attempts
    :param delay: initial delay in seconds between retries
    :param backoff: exponential backoff multiplier
    :return: decorator function
    """
    def decorator(func: F) -> F:
        @wraps(func)
        def wrapper(*args: Any, **kwargs: Any) -> Any:
            last_exception: Exception | None = None

            for attempt in range(1, max_attempts + 1):
                try:
                    return func(*args, **kwargs)
                except Exception as e:
                    last_exception = e
                    if attempt < max_attempts:
                        wait_time = delay * (backoff ** (attempt - 1))
                        printf(
                            f'  └─ Attempt {attempt}/{max_attempts} failed, retrying in {wait_time:.1f}s...',
                            fg='yellow',
                        )
                        time.sleep(wait_time)
                    else:
                        printf(f'  └─ All {max_attempts} attempts failed', fg='red')

            if last_exception:
                raise last_exception
            return None

        return wrapper          # type: ignore[return-value]
    return decorator
