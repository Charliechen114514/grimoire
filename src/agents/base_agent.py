"""Agent 基类 — prompt 加载 / API 调用 / 重试 / Pydantic 验证"""
import asyncio
import json
import re
import time
from abc import ABC, abstractmethod
from pathlib import Path
from typing import TypeVar

import anthropic
from pydantic import BaseModel

from src.config import (
    ANTHROPIC_API_KEY,
    ANTHROPIC_BASE_URL,
    MAX_RETRIES,
    MAX_TOKENS,
    PROMPTS_DIR,
)
from src.log import logger

T = TypeVar("T", bound=BaseModel)

_BASE_DELAY = 2.0  # 指数退避基础延迟（秒）

# 全局 API 并发信号量，在首次使用时初始化
_api_semaphore: asyncio.Semaphore | None = None


def get_api_semaphore() -> asyncio.Semaphore:
    """获取或初始化全局 API 并发信号量。"""
    global _api_semaphore
    if _api_semaphore is None:
        from src.config import MAX_CONCURRENT_CHAPTERS
        _api_semaphore = asyncio.Semaphore(MAX_CONCURRENT_CHAPTERS * 2)
    return _api_semaphore


class BaseAgent(ABC):
    """所有 Agent 的基类，提供 prompt 加载、API 调用、JSON 解析能力。"""

    def __init__(self, agent_name: str, model: str | None = None) -> None:
        self.agent_name = agent_name
        self._model = model  # alias 或原始名，在 call_api 时通过 resolve_model 解析
        self._client: anthropic.Anthropic | None = None
        self._async_client: anthropic.AsyncAnthropic | None = None
        logger.debug("Agent '{}' initialized, model_override={}", agent_name, model)

    @property
    def model_name(self) -> str:
        """解析后的实际模型名称。优先级：CLI --model > GRIMOIRE_MODEL env > 默认 sonnet。"""
        from src.config import resolve_model
        return resolve_model(self._model)

    @property
    def client(self) -> anthropic.Anthropic:
        if self._client is None:
            kwargs: dict = {"api_key": ANTHROPIC_API_KEY}
            if ANTHROPIC_BASE_URL:
                kwargs["base_url"] = ANTHROPIC_BASE_URL
            self._client = anthropic.Anthropic(**kwargs)
        return self._client

    @property
    def async_client(self) -> anthropic.AsyncAnthropic:
        if self._async_client is None:
            kwargs: dict = {"api_key": ANTHROPIC_API_KEY}
            if ANTHROPIC_BASE_URL:
                kwargs["base_url"] = ANTHROPIC_BASE_URL
            self._async_client = anthropic.AsyncAnthropic(**kwargs)
        return self._async_client

    def load_prompt(self, prompt_type: str) -> str:
        """
        从 prompts/{type}/{agent_name}_{type}.md 加载 prompt 内容。

        Args:
            prompt_type: "system" 或 "user"

        Returns:
            prompt 文件的文本内容
        """
        path = PROMPTS_DIR / prompt_type / f"{self.agent_name}_{prompt_type}.md"
        if not path.exists():
            raise FileNotFoundError(f"Prompt not found: {path}")
        content = path.read_text(encoding="utf-8")
        logger.debug("[{}] Loaded {} prompt: {} chars", self.agent_name, prompt_type, len(content))
        return content

    def call_api(
        self,
        system: str,
        user: str,
        max_tokens: int | None = None,
    ) -> str:
        """
        调用 Anthropic API，带指数退避重试。

        Args:
            system: 系统提示词
            user: 用户消息
            max_tokens: 最大输出 token 数（默认使用 config.MAX_TOKENS）

        Returns:
            模型输出的文本内容

        Raises:
            RuntimeError: 超过最大重试次数
        """
        tokens = max_tokens or MAX_TOKENS
        logger.debug(
            "[{}] call_api: model={}, max_tokens={}, system={} chars, user={} chars",
            self.agent_name, self.model_name, tokens, len(system), len(user),
        )
        start = time.time()

        for attempt in range(MAX_RETRIES):
            try:
                resp = self.client.messages.create(
                    model=self.model_name,
                    max_tokens=tokens,
                    system=system,
                    messages=[{"role": "user", "content": user}],
                )
                elapsed = time.time() - start
                output_text = resp.content[0].text
                logger.info(
                    "[{}] API call completed: model={}, attempt={}, "
                    "input_tokens={}, output_tokens={}, elapsed={:.1f}s",
                    self.agent_name, self.model_name, attempt + 1,
                    getattr(resp.usage, "input_tokens", "?"),
                    getattr(resp.usage, "output_tokens", "?"),
                    elapsed,
                )
                return output_text

            except anthropic.APIError as e:
                delay = _BASE_DELAY * (2**attempt)
                logger.warning(
                    "[{}] API error (attempt {}/{}): {} — retry in {:.1f}s",
                    self.agent_name, attempt + 1, MAX_RETRIES, e, delay,
                )
                if attempt < MAX_RETRIES - 1:
                    time.sleep(delay)
                else:
                    raise RuntimeError(
                        f"[{self.agent_name}] API failed after {MAX_RETRIES} attempts: {e}"
                    ) from e

            except Exception as e:
                delay = _BASE_DELAY * (2**attempt)
                logger.error(
                    "[{}] Unexpected error (attempt {}/{}): {}",
                    self.agent_name, attempt + 1, MAX_RETRIES, e,
                )
                if attempt < MAX_RETRIES - 1:
                    time.sleep(delay)
                else:
                    raise RuntimeError(
                        f"[{self.agent_name}] Failed after {MAX_RETRIES} attempts: {e}"
                    ) from e

        raise RuntimeError(f"[{self.agent_name}] Unreachable")  # pragma: no cover

    async def async_call_api(
        self,
        system: str,
        user: str,
        max_tokens: int | None = None,
    ) -> str:
        """
        异步调用 Anthropic API，带全局并发信号量和指数退避重试。

        Args/Returns/Raises: 同 call_api
        """
        tokens = max_tokens or MAX_TOKENS
        logger.debug(
            "[{}] async_call_api: model={}, max_tokens={}, system={} chars, user={} chars",
            self.agent_name, self.model_name, tokens, len(system), len(user),
        )
        start = time.time()
        sem = get_api_semaphore()

        for attempt in range(MAX_RETRIES):
            async with sem:
                try:
                    resp = await self.async_client.messages.create(
                        model=self.model_name,
                        max_tokens=tokens,
                        system=system,
                        messages=[{"role": "user", "content": user}],
                    )
                    elapsed = time.time() - start
                    output_text = resp.content[0].text
                    logger.info(
                        "[{}] Async API call completed: model={}, attempt={}, "
                        "input_tokens={}, output_tokens={}, elapsed={:.1f}s",
                        self.agent_name, self.model_name, attempt + 1,
                        getattr(resp.usage, "input_tokens", "?"),
                        getattr(resp.usage, "output_tokens", "?"),
                        elapsed,
                    )
                    return output_text

                except anthropic.APIError as e:
                    delay = _BASE_DELAY * (2**attempt)
                    logger.warning(
                        "[{}] API error (attempt {}/{}): {} — retry in {:.1f}s",
                        self.agent_name, attempt + 1, MAX_RETRIES, e, delay,
                    )
                    if attempt < MAX_RETRIES - 1:
                        await asyncio.sleep(delay)
                    else:
                        raise RuntimeError(
                            f"[{self.agent_name}] API failed after {MAX_RETRIES} attempts: {e}"
                        ) from e

                except Exception as e:
                    delay = _BASE_DELAY * (2**attempt)
                    logger.error(
                        "[{}] Unexpected error (attempt {}/{}): {}",
                        self.agent_name, attempt + 1, MAX_RETRIES, e,
                    )
                    if attempt < MAX_RETRIES - 1:
                        await asyncio.sleep(delay)
                    else:
                        raise RuntimeError(
                            f"[{self.agent_name}] Failed after {MAX_RETRIES} attempts: {e}"
                        ) from e

        raise RuntimeError(f"[{self.agent_name}] Unreachable")  # pragma: no cover

    def parse_json(self, raw: str, model: type[T]) -> T:
        """
        从 LLM 输出中提取 JSON 并通过 Pydantic 验证。
        自动处理 ```json ... ``` 包裹的情况。

        Args:
            raw: LLM 原始输出
            model: Pydantic model 类

        Returns:
            验证后的 Pydantic 模型实例

        Raises:
            ValueError: JSON 解析或 Pydantic 验证失败
        """
        text = raw.strip()

        # 处理 ```json ... ``` 包裹
        json_match = re.search(r"```(?:json)?\s*\n?(.*?)```", text, re.DOTALL)
        if json_match:
            text = json_match.group(1).strip()

        try:
            data = json.loads(text)
        except json.JSONDecodeError as e:
            logger.error("[{}] JSON parse failed: {} | Raw preview: {}", self.agent_name, e, text[:200])
            raise ValueError(f"JSON parse failed: {e}\nRaw: {text[:500]}") from e

        try:
            result = model.model_validate(data)
        except Exception as e:
            logger.error("[{}] Pydantic validation failed: {} | Data keys: {}", self.agent_name, e, list(data.keys()))
            raise
        logger.debug("[{}] Parsed JSON -> {} (fields: {})", self.agent_name, model.__name__, list(data.keys()))
        return result

    @abstractmethod
    def run(self, **kwargs) -> BaseModel | str:
        """子类实现具体的 Agent 逻辑。"""
        ...
