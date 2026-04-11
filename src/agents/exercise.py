"""ExerciseAgent — 基于知识点生成梯度练习题"""
from pydantic import BaseModel

from src.agents.base_agent import BaseAgent
from src.log import logger


class Exercise(BaseModel):
    """单道练习题。"""

    question: str
    difficulty: str  # "understanding" | "application" | "thinking"
    answer: str
    explanation: str


class ExerciseOutput(BaseModel):
    """ExerciseAgent 的输出模型。"""

    exercises: list[Exercise]


class ExerciseAgent(BaseAgent):
    """基于知识点生成 3-5 道梯度练习题。"""

    def __init__(self, model: str | None = None) -> None:
        super().__init__("exercise", model=model)

    def run(
        self,
        chapter_text: str,
        chapter_idx: int,
        concepts: str,
    ) -> ExerciseOutput:
        """
        生成练习题。

        Args:
            chapter_text: 章节原文（截短版用于参考）
            chapter_idx: 章节编号
            concepts: ConceptAgent 输出的 JSON 字符串

        Returns:
            ExerciseOutput 包含 3-5 道练习题
        """
        system = self.load_prompt("system")
        user_template = self.load_prompt("user")

        user = user_template.format(
            chapter_idx=chapter_idx,
            concepts_json=concepts,
            chapter_text=chapter_text[:30000],
        )

        raw = self.call_api(system=system, user=user, max_tokens=4096)
        result = self.parse_json(raw, ExerciseOutput)
        logger.info(
            "Generated {} exercises (difficulties: {})",
            len(result.exercises),
            [e.difficulty for e in result.exercises],
        )
        return result

    async def async_run(
        self,
        chapter_text: str,
        chapter_idx: int,
        concepts: str,
    ) -> ExerciseOutput:
        """异步版本：生成练习题。"""
        system = self.load_prompt("system")
        user_template = self.load_prompt("user")

        user = user_template.format(
            chapter_idx=chapter_idx,
            concepts_json=concepts,
            chapter_text=chapter_text[:30000],
        )

        raw = await self.async_call_api(system=system, user=user, max_tokens=4096)
        result = self.parse_json(raw, ExerciseOutput)
        logger.info(
            "Generated {} exercises (difficulties: {})",
            len(result.exercises),
            [e.difficulty for e in result.exercises],
        )
        return result
