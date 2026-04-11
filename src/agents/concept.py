"""ConceptAgent — 从章节原文中提取核心知识点"""
import json
import logging
from typing import Any

from pydantic import BaseModel

from src.agents.base_agent import BaseAgent

logger = logging.getLogger(__name__)


class Concept(BaseModel):
    """单个技术概念。"""

    name: str
    definition: str
    location: str
    is_new: bool


class ConceptOutput(BaseModel):
    """ConceptAgent 的输出模型。"""

    concepts: list[Concept]


class ConceptAgent(BaseAgent):
    """从章节原文中提取核心知识点。"""

    def __init__(self) -> None:
        super().__init__("concept")

    def run(
        self,
        chapter_text: str,
        glossary: dict[str, Any] | None = None,
        truncate: bool = True,
    ) -> ConceptOutput:
        """
        提取章节中的技术概念。

        Args:
            chapter_text: 章节原文
            glossary: 已有词汇表 {"概念名": {"definition": ..., "first_seen_chapter": ...}}
            truncate: 是否截断输入文本（verbose 模式下传 False）

        Returns:
            ConceptOutput 包含所有提取的概念
        """
        system = self.load_prompt("system")
        user_template = self.load_prompt("user")

        # 构建 glossary 文本
        glossary_text = "（无已有词汇表）"
        if glossary:
            lines = []
            for name, info in glossary.items():
                lines.append(f"- {name}：{info['definition']}（首见 Ch.{info['first_seen_chapter']}）")
            glossary_text = "\n".join(lines)

        text = chapter_text[:60000] if truncate else chapter_text
        user = user_template.format(
            chapter_text=text,
            glossary_text=glossary_text,
        )

        raw = self.call_api(system=system, user=user, max_tokens=4096)
        result = self.parse_json(raw, ConceptOutput)
        logger.info(
            "Extracted %d concepts (%d new)",
            len(result.concepts),
            sum(1 for c in result.concepts if c.is_new),
        )
        return result

    async def async_run(
        self,
        chapter_text: str,
        glossary: dict[str, Any] | None = None,
        truncate: bool = True,
    ) -> ConceptOutput:
        """异步版本：提取章节中的技术概念。"""
        system = self.load_prompt("system")
        user_template = self.load_prompt("user")

        glossary_text = "（无已有词汇表）"
        if glossary:
            lines = []
            for name, info in glossary.items():
                lines.append(f"- {name}：{info['definition']}（首见 Ch.{info['first_seen_chapter']}）")
            glossary_text = "\n".join(lines)

        text = chapter_text[:60000] if truncate else chapter_text
        user = user_template.format(
            chapter_text=text,
            glossary_text=glossary_text,
        )

        raw = await self.async_call_api(system=system, user=user, max_tokens=4096)
        result = self.parse_json(raw, ConceptOutput)
        logger.info(
            "Extracted %d concepts (%d new)",
            len(result.concepts),
            sum(1 for c in result.concepts if c.is_new),
        )
        return result
