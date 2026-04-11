"""WritingAgent — 基于章节原文和知识点生成教程正文"""
import json
import logging

from src.agents.base_agent import BaseAgent
from src.config import WRITING_STYLE_PATH

logger = logging.getLogger(__name__)


class WritingAgent(BaseAgent):
    """基于章节原文和知识点生成符合个人风格的教程正文。"""

    def __init__(self) -> None:
        super().__init__("writing")

    def run(
        self,
        chapter_text: str,
        chapter_idx: int,
        concepts: str,
    ) -> str:
        """
        生成教程正文。

        Args:
            chapter_text: 章节原文
            chapter_idx: 章节编号
            concepts: ConceptAgent 输出的 JSON 字符串

        Returns:
            Markdown 格式的教程正文
        """
        writing_style = WRITING_STYLE_PATH.read_text(encoding="utf-8")
        system_template = self.load_prompt("system")
        system = system_template.format(WRITING_STYLE=writing_style)

        user_template = self.load_prompt("user")
        user = user_template.format(
            chapter_idx=chapter_idx,
            concepts_json=concepts,
            chapter_text=chapter_text[:60000],
        )

        raw = self.call_api(system=system, user=user)
        logger.info("WritingAgent produced %d chars", len(raw))
        return raw
