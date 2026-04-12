"""FixAgent — 根据审查反馈对教程进行最小化修复"""
from src.agents.base_agent import BaseAgent
from src.agents.review import ChapterReview
from src.log import logger


class FixAgent(BaseAgent):
    """根据审查反馈对教程进行最小化修复。"""

    def __init__(self, model: str | None = None) -> None:
        super().__init__("fix", model=model)

    def run(
        self,
        tutorial_markdown: str,
        review: ChapterReview,
        writing_style: str,
        chapter_label: str,
    ) -> str:
        """
        根据审查反馈修复教程。

        Args:
            tutorial_markdown: 当前教程 Markdown
            review: 审查结果（包含分数和问题列表）
            writing_style: 写作风格参考
            chapter_label: 显示标签，如 "Ch.3" 或 "Ch.3.2"

        Returns:
            修复后的完整 Markdown
        """
        system = self.load_prompt("system")
        user_template = self.load_prompt("user")

        # 构建评分摘要
        scores_summary = "\n".join(
            f"- **{s.dimension}**: {s.score}/10 — {s.rationale}"
            for s in review.scores
        )

        # 构建问题列表
        issues_text = ""
        for issue in review.issues:
            issues_text += (
                f"- [{issue.severity.upper()}] **{issue.dimension}** "
                f"({issue.location}): {issue.issue}\n"
                f"  → 建议：{issue.suggestion}\n"
            )

        if not issues_text:
            issues_text = "（无具体问题，但整体评分未通过）"

        user = user_template.format(
            chapter_label=chapter_label,
            scores_summary=scores_summary,
            issues_text=issues_text,
            writing_style=writing_style,
            tutorial_markdown=tutorial_markdown[:60000],
        )

        raw = self.call_api(system=system, user=user, max_tokens=16000)
        logger.info(
            "FixAgent {}: {} chars input → {} chars output",
            chapter_label, len(tutorial_markdown), len(raw),
        )
        return raw
