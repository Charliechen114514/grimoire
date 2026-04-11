"""Orchestrator — 串联 4 个 Agent 处理单个章节"""
import json
import logging
import os
import tempfile
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from src.agents.concept import ConceptAgent, ConceptOutput
from src.agents.exercise import ExerciseAgent, ExerciseOutput
from src.agents.tldr import TLDRAgent
from src.agents.writing import WritingAgent
from src.config import book_output_dir

logger = logging.getLogger(__name__)

_MAX_RETRIES = 2  # Pydantic 验证失败时的重试次数


@dataclass
class ChapterResult:
    """Pipeline 处理单章的结果。"""

    output_path: Path
    concepts: ConceptOutput


def run_chapter_pipeline(
    chapter_text: str,
    chapter_idx: int,
    book_slug: str,
    glossary: dict[str, Any] | None = None,
) -> Path:
    """
    串联 4 个 Agent 处理单个章节。

    流程：ConceptAgent → WritingAgent + ExerciseAgent → TLDRAgent → 合并输出

    Args:
        chapter_text: 章节原文
        chapter_idx: 章节编号（1-indexed）
        book_slug: 书籍短名
        glossary: 已有词汇表（Phase 3 用）

    Returns:
        输出文件路径 output/{book_slug}/tutorials/ch{NN}.md

    Raises:
        RuntimeError: Agent 执行失败
    """
    logger.info("=== Pipeline started: %s Ch.%d ===", book_slug, chapter_idx)

    # Step 1: ConceptAgent
    concept_agent = ConceptAgent()
    concepts_result = _run_with_retry(
        lambda: concept_agent.run(chapter_text=chapter_text, glossary=glossary),
        agent_name="ConceptAgent",
    )
    concepts_json = concepts_result.model_dump_json(indent=2)
    logger.info("Concepts: %d extracted", len(concepts_result.concepts))

    # Step 2: WritingAgent（依赖 concepts）
    writing_agent = WritingAgent()
    writing_result = _run_with_retry(
        lambda: writing_agent.run(
            chapter_text=chapter_text,
            chapter_idx=chapter_idx,
            concepts=concepts_json,
        ),
        agent_name="WritingAgent",
    )
    logger.info("Writing: %d chars", len(writing_result))

    # Step 3: ExerciseAgent（依赖 concepts）
    exercise_agent = ExerciseAgent()
    exercise_result = _run_with_retry(
        lambda: exercise_agent.run(
            chapter_text=chapter_text,
            chapter_idx=chapter_idx,
            concepts=concepts_json,
        ),
        agent_name="ExerciseAgent",
    )
    logger.info("Exercises: %d generated", len(exercise_result.exercises))

    # Step 4: TLDRAgent（依赖 writing output）
    tldr_agent = TLDRAgent()
    tldr_result = _run_with_retry(
        lambda: tldr_agent.run(writing_output=writing_result, chapter_idx=chapter_idx),
        agent_name="TLDRAgent",
    )
    logger.info("TLDR: %d chars", len(tldr_result))

    # Step 5: 合并输出
    merged = _merge_outputs(writing_result, exercise_result, tldr_result, chapter_idx)

    # Step 6: 写入文件
    output_dir = book_output_dir(book_slug)
    filename = f"ch{chapter_idx:02d}.md"
    output_path = output_dir / filename
    _atomic_write(output_path, merged)

    logger.info("=== Pipeline completed: %s ===", output_path)
    return ChapterResult(output_path=output_path, concepts=concepts_result)


def _run_with_retry(func: callable, agent_name: str) -> Any:
    """运行 Agent 函数，Pydantic 验证失败时重试。"""
    last_error: Exception | None = None
    for attempt in range(_MAX_RETRIES + 1):
        try:
            return func()
        except (ValueError, Exception) as e:
            last_error = e
            if attempt < _MAX_RETRIES:
                logger.warning(
                    "[%s] Attempt %d failed: %s — retrying",
                    agent_name, attempt + 1, e,
                )
            else:
                logger.error("[%s] All %d attempts failed", agent_name, _MAX_RETRIES + 1)
    raise RuntimeError(f"[{agent_name}] Failed after {_MAX_RETRIES + 1} attempts: {last_error}")


def _merge_outputs(
    writing: str,
    exercises: ExerciseOutput,
    tldr: str,
    chapter_idx: int,
) -> str:
    """合并 4 个 Agent 的输出为最终 Markdown。"""
    parts: list[str] = []

    # 教程正文
    parts.append(writing.strip())

    # 练习题
    parts.append("\n\n---\n\n## 练习题\n")
    for i, ex in enumerate(exercises.exercises, 1):
        parts.append(f"\n### 练习 {i}：{ex.difficulty}\n")
        parts.append(f"**题目**：{ex.question}\n")
        parts.append(f"<details><summary>答案与解析</summary>\n\n")
        parts.append(f"**答案**：{ex.answer}\n\n")
        parts.append(f"**解析**：{ex.explanation}\n\n")
        parts.append(f"</details>\n")

    # 要点提炼
    parts.append("\n---\n\n## 要点提炼\n\n")
    parts.append(tldr.strip())

    return "\n".join(parts)


def _atomic_write(path: Path, content: str) -> None:
    """原子写入文件（temp + rename）。"""
    path.parent.mkdir(parents=True, exist_ok=True)
    fd, tmp_path = tempfile.mkstemp(suffix=".md", dir=str(path.parent))
    try:
        with os.fdopen(fd, "w", encoding="utf-8") as f:
            f.write(content)
        os.replace(tmp_path, path)
    except BaseException:
        if os.path.exists(tmp_path):
            os.unlink(tmp_path)
        raise
