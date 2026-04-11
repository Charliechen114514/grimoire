"""ReviewAgent — 审核教程章节的风格一致性、难度曲线、概念密度"""
import logging

from pydantic import BaseModel

from src.agents.base_agent import BaseAgent

logger = logging.getLogger(__name__)


class DimensionScore(BaseModel):
    """单个审核维度的评分。"""

    dimension: str   # "style" | "difficulty" | "density"
    score: int       # 1-10, >=7 通过
    rationale: str


class ReviewIssue(BaseModel):
    """单个审核发现。"""

    dimension: str   # "style" | "difficulty" | "density"
    location: str    # e.g. "前言段", "4.2.3 节"
    issue: str
    suggestion: str
    severity: str    # "high" | "medium" | "low"


class ChapterReview(BaseModel):
    """单章审核结果。"""

    scores: list[DimensionScore]
    issues: list[ReviewIssue]
    overall_pass: bool


class ReviewAgent(BaseAgent):
    """审核单个教程章节的质量。"""

    def __init__(self) -> None:
        super().__init__("review")

    def run(
        self,
        tutorial_markdown: str,
        chapter_idx: int,
        writing_style: str,
    ) -> ChapterReview:
        """
        审核单章教程。

        Args:
            tutorial_markdown: 教程完整 Markdown
            chapter_idx: 章节编号
            writing_style: writing_style.md 全文

        Returns:
            ChapterReview 包含三维度评分和问题列表
        """
        system = self.load_prompt("system")
        user_template = self.load_prompt("user")

        user = user_template.format(
            chapter_idx=chapter_idx,
            writing_style=writing_style,
            tutorial_markdown=tutorial_markdown[:60000],
        )

        raw = self.call_api(system=system, user=user, max_tokens=4096)
        result = self.parse_json(raw, ChapterReview)
        passed = "PASS" if result.overall_pass else "FAIL"
        logger.info(
            "Review Ch.%d: %s (scores: %s, issues: %d)",
            chapter_idx,
            passed,
            [(s.dimension, s.score) for s in result.scores],
            len(result.issues),
        )
        return result
