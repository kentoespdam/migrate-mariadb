import logging
import time
from collections.abc import Callable
from typing import TypeVar

import mysql.connector

T = TypeVar("T")
logger = logging.getLogger("pysync_maria.db.retry")

def retry_with_backoff(
    fn: Callable[[], T],
    *,
    retries: int = 3,
    on_exceptions: tuple[type[Exception], ...] = (
        mysql.connector.OperationalError,
        mysql.connector.InterfaceError,
    ),
    on_retry: Callable[[int, Exception], None] | None = None,
) -> T:
    """
    Retry a function with exponential backoff.
    """
    retry_count = 0
    last_err: Exception | None = None

    while retry_count < retries:
        try:
            return fn()
        except on_exceptions as e:
            last_err = e
            retry_count += 1
            if retry_count >= retries:
                break

            wait_time = 2 ** retry_count
            if on_retry:
                on_retry(retry_count, e)
            else:
                logger.warning(
                    f"Retry {retry_count}/{retries} after {wait_time}s: {e}"
                )
            time.sleep(wait_time)

    raise last_err if last_err else Exception("Retry failed")
