"""TLDRAgent — 从教程正文中提炼核心要点"""
import logging

from src.agents.base_agent import BaseAgent

logger = logging.getLogger(__name__)


class TLDRAgent(BaseAgent):
    """从 WritingAgent 输出中提炼不超过 5 条核心要点。"""

    def __init__(self) -> None:
        super().__init__("tldr")

    def run(self, writing_output: str, chapter_idx: int) -> str:
        """
        提炼教程核心要点。

        Args:
            writing_output: WritingAgent 生成的教程正文
            chapter_idx: 章节编号

        Returns:
            Markdown 格式的要点提炼（自然段落形式）
        """
        system = self.load_prompt("system")
        user_template = self.load_prompt("user")

        user = user_template.format(
            chapter_idx=chapter_idx,
            writing_output=writing_output[:30000],
        )

        raw = self.call_api(system=system, user=user, max_tokens=2048)
        logger.info("TLDRAgent produced %d chars", len(raw))
        return raw
