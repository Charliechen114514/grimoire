"""视觉 LLM 客户端 — 通过智谱 OpenAI 兼容端点调用 glm-4.5v / glm-4v-plus。

⚠️ 重要陷阱：智谱 Anthropic 兼容端点 (/api/anthropic，项目 base_agent 用的那条)
   会静默丢弃图像 content block，glm-4.7 凭空幻觉错误内容。
   视觉调用**必须**走 OpenAI 兼容端点 (ZHIPU_VISION_URL)，图像才会真正传进模型。

重试 / 指数退避模式复用自 base_agent.py。并发由调用方（parser）用 asyncio.Semaphore 控制。
"""
from __future__ import annotations

import asyncio
import base64
import time

import httpx

from src.config import ANTHROPIC_API_KEY, MAX_RETRIES, ZHIPU_VISION_URL
from src.log import logger

_BASE_DELAY = 2.0  # 指数退避基础延迟（秒）


def _default_max_tokens(model: str) -> int:
    """按模型返回安全的 max_tokens。

    智谱各视觉模型输出上限不同：glm-4v-plus / flash / air 类轻量模型上限 2048，
    超过会 HTTP 400 (code 1210)；glm-4.5v 等旗舰支持更大。密集教材页可能超 2048，
    故默认用 glm-4.5v 避免截断。
    """
    m = model.lower()
    if any(k in m for k in ("4v-plus", "flash", "air", "plus")):
        return 2048
    return 4096


class VisionError(RuntimeError):
    """视觉调用失败（重试耗尽）。"""


async def vision_transcribe(
    image_bytes: bytes,
    prompt: str,
    *,
    model: str,
    media_type: str = "image/png",
    max_tokens: int | None = None,
    timeout: float = 180,
) -> str:
    """把一张图片发给视觉模型，返回转写文本。

    Args:
        image_bytes: 图片原始字节（PNG/JPEG）
        prompt: 文字指令
        model: 智谱视觉模型名（glm-4.5v / glm-4v-plus 等）
        media_type: 图片 MIME 类型
        max_tokens: 输出上限
        timeout: 单次请求超时（秒）

    Raises:
        VisionError: 超过 MAX_RETRIES 次重试仍失败
    """
    if not ANTHROPIC_API_KEY:
        raise VisionError("ANTHROPIC_API_KEY 未配置（.env 缺失或为空）")

    if max_tokens is None:
        max_tokens = _default_max_tokens(model)

    b64 = base64.b64encode(image_bytes).decode()
    body = {
        "model": model,
        "max_tokens": max_tokens,
        "messages": [
            {
                "role": "user",
                "content": [
                    {"type": "image_url", "image_url": {"url": f"data:{media_type};base64,{b64}"}},
                    {"type": "text", "text": prompt},
                ],
            }
        ],
    }
    headers = {
        "Authorization": f"Bearer {ANTHROPIC_API_KEY}",
        "Content-Type": "application/json",
    }

    last_err: Exception | None = None
    for attempt in range(MAX_RETRIES):
        try:
            start = time.time()
            async with httpx.AsyncClient(timeout=timeout) as client:
                resp = await client.post(ZHIPU_VISION_URL, headers=headers, json=body)
            if resp.status_code != 200:
                raise RuntimeError(f"HTTP {resp.status_code}: {resp.text[:300]}")

            data = resp.json()
            content = data["choices"][0]["message"]["content"]
            usage = data.get("usage", {})
            logger.info(
                "[vision] ok model={} in={} out={} {:.1f}s",
                model,
                usage.get("prompt_tokens", "?"),
                usage.get("completion_tokens", "?"),
                time.time() - start,
            )
            return content

        except Exception as e:
            last_err = e
            if attempt < MAX_RETRIES - 1:
                delay = _BASE_DELAY * (2**attempt)
                logger.warning(
                    "[vision] 重试 {}/{}: {} — 等待 {:.0f}s",
                    attempt + 1, MAX_RETRIES, str(e)[:140], delay,
                )
                await asyncio.sleep(delay)

    raise VisionError(f"视觉调用 {MAX_RETRIES} 次后仍失败: {last_err}")
