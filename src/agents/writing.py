"""WritingAgent — 基于章节原文和知识点生成教程正文"""
import json
import logging

from src.agents.base_agent import BaseAgent
from src.config import VERBOSE_MAX_TOKENS, WRITING_STYLE_PATH

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

    async def async_run(
        self,
        chapter_text: str,
        chapter_idx: int,
        concepts: str,
    ) -> str:
        """异步版本：生成教程正文。"""
        writing_style = WRITING_STYLE_PATH.read_text(encoding="utf-8")
        system_template = self.load_prompt("system")
        system = system_template.format(WRITING_STYLE=writing_style)

        user_template = self.load_prompt("user")
        user = user_template.format(
            chapter_idx=chapter_idx,
            concepts_json=concepts,
            chapter_text=chapter_text[:60000],
        )

        raw = await self.async_call_api(system=system, user=user)
        logger.info("WritingAgent produced %d chars", len(raw))
        return raw

    def run_verbose(
        self,
        section_text: str,
        section_title: str,
        section_idx: int,
        total_sections: int,
        chapter_idx: int,
        concepts: str,
        previous_summary: str = "",
    ) -> str:
        """
        Verbose 模式：对单个小节进行忠实改写。

        Args:
            section_text: 小节原文
            section_title: 小节标题
            section_idx: 小节索引（0-indexed）
            total_sections: 总小节数
            chapter_idx: 章节编号
            concepts: ConceptAgent 输出的 JSON 字符串
            previous_summary: 上一节改写结果的尾迹摘要

        Returns:
            Markdown 格式的小节改写结果
        """
        writing_style = WRITING_STYLE_PATH.read_text(encoding="utf-8")
        system_template = self.load_prompt("system")
        # 加载 verbose 模式专用提示词
        system_template = self._load_verbose_prompt("system")
        system = system_template.format(WRITING_STYLE=writing_style)

        # 根据节位置生成提示
        if section_idx == 0:
            position_hint = (
                "这是本章的**第一节**。请先写一个章节引言/动机段，"
                "介绍本章要讲什么、为什么重要、旧方案为什么不行，"
                "然后自然过渡到本节内容。"
            )
        elif section_idx == total_sections - 1:
            position_hint = (
                "这是本章的**最后一节**。在本节内容改写完成后，"
                "请追加一个章节总结段，用连贯文字总结本章核心收获。"
            )
        else:
            position_hint = (
                f"这是本章的第 {section_idx + 1} 节（共 {total_sections} 节），"
                "中间节，正常改写并注意从上一节自然承接。"
            )

        user_template = self._load_verbose_prompt("user")
        user = user_template.format(
            chapter_idx=chapter_idx,
            section_idx=section_idx + 1,
            total_sections=total_sections,
            section_title=section_title,
            section_position_hint=position_hint,
            concepts_json=concepts,
            previous_summary=previous_summary or "（这是第一节，没有上一节内容）",
            section_text=section_text,
        )

        raw = self.call_api(system=system, user=user, max_tokens=VERBOSE_MAX_TOKENS)
        logger.info(
            "WritingAgent (verbose) section %d/%d '%s': %d chars",
            section_idx + 1, total_sections, section_title[:40], len(raw),
        )
        return raw

    async def async_run_verbose(
        self,
        section_text: str,
        section_title: str,
        section_idx: int,
        total_sections: int,
        chapter_idx: int,
        concepts: str,
        previous_summary: str = "",
    ) -> str:
        """异步版本：Verbose 模式单小节忠实改写。"""
        writing_style = WRITING_STYLE_PATH.read_text(encoding="utf-8")
        system_template = self._load_verbose_prompt("system")
        system = system_template.format(WRITING_STYLE=writing_style)

        if section_idx == 0:
            position_hint = (
                "这是本章的**第一节**。请先写一个章节引言/动机段，"
                "介绍本章要讲什么、为什么重要、旧方案为什么不行，"
                "然后自然过渡到本节内容。"
            )
        elif section_idx == total_sections - 1:
            position_hint = (
                "这是本章的**最后一节**。在本节内容改写完成后，"
                "请追加一个章节总结段，用连贯文字总结本章核心收获。"
            )
        else:
            position_hint = (
                f"这是本章的第 {section_idx + 1} 节（共 {total_sections} 节），"
                "中间节，正常改写并注意从上一节自然承接。"
            )

        user_template = self._load_verbose_prompt("user")
        user = user_template.format(
            chapter_idx=chapter_idx,
            section_idx=section_idx + 1,
            total_sections=total_sections,
            section_title=section_title,
            section_position_hint=position_hint,
            concepts_json=concepts,
            previous_summary=previous_summary or "（这是第一节，没有上一节内容）",
            section_text=section_text,
        )

        raw = await self.async_call_api(system=system, user=user, max_tokens=VERBOSE_MAX_TOKENS)
        logger.info(
            "WritingAgent (verbose) section %d/%d '%s': %d chars",
            section_idx + 1, total_sections, section_title[:40], len(raw),
        )
        return raw

    def _load_verbose_prompt(self, prompt_type: str) -> str:
        """加载 verbose 模式专用提示词。"""
        path = (
            self._prompts_dir()
            / prompt_type
            / f"writing_verbose_{prompt_type}.md"
        )
        if not path.exists():
            raise FileNotFoundError(f"Verbose prompt not found: {path}")
        return path.read_text(encoding="utf-8")

    def _prompts_dir(self):
        """返回 prompts 目录路径。"""
        from src.config import PROMPTS_DIR
        return PROMPTS_DIR
