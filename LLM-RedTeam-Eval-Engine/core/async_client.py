"""异步 LLM 调用客户端。

提供高并发、带限流与指数退避重试的 OpenAI 兼容 API 调用能力。
"""

from __future__ import annotations

import asyncio
import logging
import time
from typing import Any, Dict, List, Optional

import aiohttp

from core.config import get_settings

logger = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# 自定义异常
# ---------------------------------------------------------------------------

class LLMClientError(Exception):
    """LLM 客户端通用异常基类。"""


class RateLimitError(LLMClientError):
    """HTTP 429 速率限制异常。"""


class ServerError(LLMClientError):
    """HTTP 5xx 服务端异常。"""


class MaxRetriesExceeded(LLMClientError):
    """超过最大重试次数后抛出。"""


class APIConnectionError(LLMClientError):
    """网络连接失败异常。"""


# ---------------------------------------------------------------------------
# 核心客户端
# ---------------------------------------------------------------------------

class AsyncLLMClient:
    """异步 LLM 调用客户端。

    特性：
    - 基于 ``aiohttp`` 的纯异步 HTTP 通信。
    - 使用 ``asyncio.Semaphore`` 限制最大并发请求数。
    - 对 429 / 5xx 错误进行异步指数退避重试。
    - 线程安全的会话生命周期管理。

    用法::

        client = AsyncLLMClient()
        async with client:
            reply = await client.call_llm(
                messages=[{"role": "user", "content": "Hello"}],
                model="gpt-4o",
            )
    """

    def __init__(self) -> None:
        settings = get_settings()
        self._api_key: str = settings.OPENAI_API_KEY
        self._base_url: str = settings.BASE_URL.rstrip("/")
        self._max_concurrent: int = settings.MAX_CONCURRENT_REQUESTS
        self._timeout: int = settings.REQUEST_TIMEOUT
        self._max_retries: int = settings.MAX_RETRIES
        self._backoff_base: float = settings.RETRY_BACKOFF

        self._semaphore: asyncio.Semaphore = asyncio.Semaphore(self._max_concurrent)
        self._session: Optional[aiohttp.ClientSession] = None

    # -- 生命周期管理 --------------------------------------------------------

    async def __aenter__(self) -> "AsyncLLMClient":
        await self._ensure_session()
        return self

    async def __aexit__(
        self,
        exc_type: Optional[type],
        exc_val: Optional[BaseException],
        exc_tb: Any,
    ) -> None:
        await self.close()

    async def _ensure_session(self) -> None:
        """确保 aiohttp 会话已创建（懒初始化）。"""
        if self._session is None or self._session.closed:
            headers = {
                "Authorization": f"Bearer {self._api_key}",
                "Content-Type": "application/json",
            }
            timeout = aiohttp.ClientTimeout(total=self._timeout)
            self._session = aiohttp.ClientSession(
                headers=headers,
                timeout=timeout,
            )

    async def close(self) -> None:
        """关闭底层 HTTP 会话，释放连接池资源。"""
        if self._session and not self._session.closed:
            await self._session.close()
            self._session = None

    # -- 核心调用方法 --------------------------------------------------------

    async def call_llm(
        self,
        messages: List[Dict[str, str]],
        model: str,
        temperature: float = 0.7,
        max_tokens: Optional[int] = None,
        **kwargs: Any,
    ) -> str:
        """调用 LLM chat completions API 并返回模型回复文本。

        Args:
            messages: OpenAI 格式的消息列表，每条包含 role 和 content。
            model: 目标模型名称（如 ``gpt-4o``）。
            temperature: 生成温度，控制随机性。默认 0.7。
            max_tokens: 最大生成 token 数，为 None 时使用服务端默认值。
            **kwargs: 其他传递给 API 的额外参数。

        Returns:
            模型生成的文本内容。

        Raises:
            RateLimitError: 速率限制且重试耗尽。
            ServerError: 服务端错误且重试耗尽。
            MaxRetriesExceeded: 所有重试均失败。
            APIConnectionError: 无法建立网络连接。
            LLMClientError: 其他不可恢复的请求错误。
        """
        await self._ensure_session()
        payload = self._build_payload(messages, model, temperature, max_tokens, **kwargs)
        url = f"{self._base_url}/chat/completions"

        last_exception: Optional[Exception] = None

        for attempt in range(1, self._max_retries + 1):
            try:
                async with self._semaphore:
                    response = await self._session.post(url, json=payload)

                    # -- 速率限制 ------------------------------------------------
                    if response.status == 429:
                        retry_after = self._parse_retry_after(response.headers)
                        wait = retry_after or self._backoff_base * (2 ** (attempt - 1))
                        logger.warning(
                            "[429] Rate limited, attempt %d/%d, retrying in %.1fs",
                            attempt,
                            self._max_retries,
                            wait,
                        )
                        last_exception = RateLimitError(f"429 Rate Limit (attempt {attempt})")
                        if attempt < self._max_retries:
                            await asyncio.sleep(wait)
                            continue
                        raise last_exception

                    # -- 服务端错误 ----------------------------------------------
                    if response.status >= 500:
                        wait = self._backoff_base * (2 ** (attempt - 1))
                        logger.warning(
                            "[%d] Server error, attempt %d/%d, retrying in %.1fs",
                            response.status,
                            attempt,
                            self._max_retries,
                            wait,
                        )
                        last_exception = ServerError(
                            f"{response.status} Server Error (attempt {attempt})"
                        )
                        if attempt < self._max_retries:
                            await asyncio.sleep(wait)
                            continue
                        raise last_exception

                    # -- 客户端错误（非 429） ------------------------------------
                    if response.status >= 400:
                        body = await response.text()
                        raise LLMClientError(
                            f"HTTP {response.status}: {body[:500]}"
                        )

                    # -- 成功响应 ------------------------------------------------
                    data: Dict[str, Any] = await response.json()
                    return self._extract_content(data)

            except (aiohttp.ClientError, asyncio.TimeoutError) as exc:
                wait = self._backoff_base * (2 ** (attempt - 1))
                logger.warning(
                    "Connection error (%s), attempt %d/%d, retrying in %.1fs",
                    exc,
                    attempt,
                    self._max_retries,
                    wait,
                )
                last_exception = APIConnectionError(f"Connection failed: {exc}")
                if attempt < self._max_retries:
                    await asyncio.sleep(wait)
                    continue
                raise MaxRetriesExceeded(
                    f"All {self._max_retries} retries exhausted"
                ) from last_exception

        # 不应到达此处，但作为安全网
        raise MaxRetriesExceeded(f"All {self._max_retries} retries exhausted") from last_exception

    # -- 辅助方法 ------------------------------------------------------------

    @staticmethod
    def _build_payload(
        messages: List[Dict[str, str]],
        model: str,
        temperature: float,
        max_tokens: Optional[int],
        **kwargs: Any,
    ) -> Dict[str, Any]:
        """构建 OpenAI chat completions 请求体。"""
        payload: Dict[str, Any] = {
            "model": model,
            "messages": messages,
            "temperature": temperature,
        }
        if max_tokens is not None:
            payload["max_tokens"] = max_tokens
        payload.update(kwargs)
        return payload

    @staticmethod
    def _extract_content(data: Dict[str, Any]) -> str:
        """从 API 响应 JSON 中提取回复文本。

        Raises:
            LLMClientError: 响应格式不符合预期时抛出。
        """
        try:
            return data["choices"][0]["message"]["content"]
        except (KeyError, IndexError, TypeError) as exc:
            raise LLMClientError(
                f"Unexpected API response structure: {data}"
            ) from exc

    @staticmethod
    def _parse_retry_after(headers: Dict[str, str]) -> Optional[float]:
        """尝试从响应头中解析 Retry-After 值（秒）。"""
        raw = headers.get("Retry-After") or headers.get("retry-after")
        if raw is None:
            return None
        try:
            return float(raw)
        except (ValueError, TypeError):
            return None
