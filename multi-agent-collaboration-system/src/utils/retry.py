"""重试策略"""

import asyncio
import structlog
from typing import Callable, Any
from functools import wraps

logger = structlog.get_logger()


class RetryPolicy:
    """重试策略"""

    def __init__(
        self,
        max_retries: int = 3,
        backoff: float = 1.5,
        exceptions: tuple = (Exception,),
    ):
        self.max_retries = max_retries
        self.backoff = backoff
        self.exceptions = exceptions

    async def execute(self, func: Callable, *args, **kwargs) -> Any:
        """执行函数，失败时重试"""
        last_error = None

        for attempt in range(self.max_retries):
            try:
                return await func(*args, **kwargs)
            except self.exceptions as e:
                last_error = e
                if attempt < self.max_retries - 1:
                    delay = self.backoff ** attempt
                    logger.warning(
                        "retry.attempt",
                        attempt=attempt + 1,
                        max_retries=self.max_retries,
                        delay=delay,
                        error=str(e),
                    )
                    await asyncio.sleep(delay)

        raise last_error


def with_retry(
    max_retries: int = 3,
    backoff: float = 1.5,
    exceptions: tuple = (Exception,),
):
    """重试装饰器"""
    def decorator(func):
        @wraps(func)
        async def wrapper(*args, **kwargs):
            policy = RetryPolicy(max_retries, backoff, exceptions)
            return await policy.execute(func, *args, **kwargs)
        return wrapper
    return decorator
