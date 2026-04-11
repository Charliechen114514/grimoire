"""Agent 基类 — prompt 加载 / API 调用 / 重试 / Pydantic 验证"""
import json
import logging
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
    MODEL_NAME,
    PROMPTS_DIR,
)

logger = logging.getLogger(__name__)

T = TypeVar("T", bound=BaseModel)

_BASE_DELAY = 2.0  # 指数退避基础延迟（秒）


class BaseAgent(ABC):
    """所有 Agent 的基类，提供 prompt 加载、API 调用、JSON 解析能力。"""

    def __init__(self, agent_name: str) -> None:
        self.agent_name = agent_name
        self._client: anthropic.Anthropic | None = None

    @property
    def client(self) -> anthropic.Anthropic:
        if self._client is None:
            kwargs: dict = {"api_key": ANTHROPIC_API_KEY}
            if ANTHROPIC_BASE_URL:
                kwargs["base_url"] = ANTHROPIC_BASE_URL
            self._client = anthropic.Anthropic(**kwargs)
        return self._client

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
        return path.read_text(encoding="utf-8")

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

        for attempt in range(MAX_RETRIES):
            try:
                resp = self.client.messages.create(
                    model=MODEL_NAME,
                    max_tokens=tokens,
                    system=system,
                    messages=[{"role": "user", "content": user}],
                )
                return resp.content[0].text

            except anthropic.APIError as e:
                delay = _BASE_DELAY * (2**attempt)
                logger.warning(
                    "[%s] API error (attempt %d/%d): %s — retry in %.1fs",
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
                    "[%s] Unexpected error (attempt %d/%d): %s",
                    self.agent_name, attempt + 1, MAX_RETRIES, e,
                )
                if attempt < MAX_RETRIES - 1:
                    time.sleep(delay)
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
            raise ValueError(f"JSON parse failed: {e}\nRaw: {text[:500]}") from e

        return model.model_validate(data)

    @abstractmethod
    def run(self, **kwargs) -> BaseModel | str:
        """子类实现具体的 Agent 逻辑。"""
        ...
