"""Orchestrator — 串联 4 个 Agent 处理单个章节"""
import asyncio
import json
import os
import tempfile
import time
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

from src.agents.concept import ConceptAgent, ConceptOutput
from src.agents.exercise import ExerciseAgent, ExerciseOutput
from src.agents.tldr import TLDRAgent
from src.agents.writing import WritingAgent
from src.config import book_output_dir
from src.log import logger

_MAX_RETRIES = 2  # Pydantic 验证失败时的重试次数


@dataclass
class ChapterResult:
    """Pipeline 处理单章的结果。"""

    output_path: Path  # 主索引文件 (ch{NN}.md)
    concepts: ConceptOutput
    section_paths: list[Path] = field(default_factory=list)  # 分节文件列表


def run_chapter_pipeline(
    chapter_text: str,
    chapter_idx: int,
    book_slug: str,
    glossary: dict[str, Any] | None = None,
    verbose_mode: bool = False,
    toc: list[tuple[int, str, int]] | None = None,
    model: str | None = None,
) -> ChapterResult:
    """
    串联 4 个 Agent 处理单个章节。

    流程：ConceptAgent → WritingAgent + ExerciseAgent → TLDRAgent → 合并输出

    Args:
        chapter_text: 章节原文
        chapter_idx: 章节编号（1-indexed）
        book_slug: 书籍短名
        glossary: 已有词汇表（Phase 3 用）
        verbose_mode: 是否启用 verbose 模式（自适应分节忠实改写）
        toc: pymupdf 原始 TOC，verbose 模式用于分节
        model: 模型名称或 alias（如 "haiku"/"sonnet"/"opus"）

    Returns:
        ChapterResult 包含输出文件路径和概念提取结果

    Raises:
        RuntimeError: Agent 执行失败
    """
    mode_label = "VERBOSE" if verbose_mode else "STANDARD"
    logger.info("=== Pipeline started [{}]: {} Ch.{} (input: {} chars) ===", mode_label, book_slug, chapter_idx, len(chapter_text))
    pipeline_start = time.time()

    # Auto-upgrade: 当 section_splitter 检测到多个 section 时自动升级 verbose
    pre_sections: list | None = None
    if not verbose_mode:
        from src.section_splitter import split_chapter_into_sections
        pre_sections = split_chapter_into_sections(chapter_text, chapter_idx, toc)
        if len(pre_sections) > 1:
            verbose_mode = True
            logger.info(
                "Auto-upgraded to VERBOSE: chapter {} has {} sections from text headings",
                chapter_idx, len(pre_sections),
            )

    # Step 1: ConceptAgent
    step_start = time.time()
    concept_agent = ConceptAgent(model=model)
    concepts_result = _run_with_retry(
        lambda: concept_agent.run(
            chapter_text=chapter_text,
            glossary=glossary,
            truncate=not verbose_mode,
        ),
        agent_name="ConceptAgent",
    )
    concepts_json = concepts_result.model_dump_json(indent=2)
    logger.info("Concepts: {} extracted ({:.1f}s)", len(concepts_result.concepts), time.time() - step_start)

    # Step 2: WritingAgent（依赖 concepts）
    step_start = time.time()
    writing_agent = WritingAgent(model=model)
    if verbose_mode:
        section_results, sections = _run_verbose_writing(
            writing_agent=writing_agent,
            chapter_text=chapter_text,
            chapter_idx=chapter_idx,
            concepts=concepts_json,
            toc=toc,
            pre_sections=pre_sections,
        )
        # 内部合并全文供 Exercise/TLDR 使用
        writing_result = _merge_verbose_sections(section_results)
    else:
        section_results = None
        sections = None
        writing_result = _run_with_retry(
            lambda: writing_agent.run(
                chapter_text=chapter_text,
                chapter_idx=chapter_idx,
                concepts=concepts_json,
            ),
            agent_name="WritingAgent",
        )
    logger.info("Writing: {} chars ({:.1f}s)", len(writing_result), time.time() - step_start)

    # Step 3: ExerciseAgent（依赖 concepts）
    step_start = time.time()
    exercise_agent = ExerciseAgent(model=model)
    exercise_result = _run_with_retry(
        lambda: exercise_agent.run(
            chapter_text=chapter_text,
            chapter_idx=chapter_idx,
            concepts=concepts_json,
        ),
        agent_name="ExerciseAgent",
    )
    logger.info("Exercises: {} generated ({:.1f}s)", len(exercise_result.exercises), time.time() - step_start)

    # Step 4: TLDRAgent（依赖 writing output）
    step_start = time.time()
    tldr_agent = TLDRAgent(model=model)
    tldr_result = _run_with_retry(
        lambda: tldr_agent.run(writing_output=writing_result, chapter_idx=chapter_idx),
        agent_name="TLDRAgent",
    )
    logger.info("TLDR: {} chars ({:.1f}s)", len(tldr_result), time.time() - step_start)

    # Step 5: 合并并写入文件
    output_dir = book_output_dir(book_slug)
    exercise_tldr_md = _build_exercise_tldr(exercise_result, tldr_result)

    if verbose_mode and section_results and len(section_results) > 1:
        # 多文件输出：每个分节一个文件 + 索引页
        section_paths = _write_multi_file(
            output_dir, chapter_idx, section_results, sections, exercise_tldr_md,
        )
        # 生成索引页
        index_path = _write_chapter_index(
            output_dir, chapter_idx, sections, section_paths, exercise_tldr_md,
        )
        logger.info("=== Pipeline completed: {} ({} sections, total {:.1f}s) ===", index_path, len(section_paths), time.time() - pipeline_start)
        return ChapterResult(
            output_path=index_path,
            concepts=concepts_result,
            section_paths=section_paths,
        )
    else:
        # 单文件输出（标准模式 或 只有一个分节的 verbose）
        merged = _merge_outputs(writing_result, exercise_result, tldr_result, chapter_idx)
        filename = f"ch{chapter_idx:02d}.md"
        output_path = output_dir / filename
        _atomic_write(output_path, merged)
        logger.info("=== Pipeline completed: {} (total {:.1f}s) ===", output_path, time.time() - pipeline_start)
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
                    "[{}] Attempt {} failed: {} — retrying",
                    agent_name, attempt + 1, e,
                )
            else:
                logger.error("[{}] All {} attempts failed", agent_name, _MAX_RETRIES + 1)
    raise RuntimeError(f"[{agent_name}] Failed after {_MAX_RETRIES + 1} attempts: {last_error}")


async def _async_run_with_retry(func: callable, agent_name: str) -> Any:
    """异步运行 Agent 函数，Pydantic 验证失败时重试。"""
    last_error: Exception | None = None
    for attempt in range(_MAX_RETRIES + 1):
        try:
            return await func()
        except (ValueError, Exception) as e:
            last_error = e
            if attempt < _MAX_RETRIES:
                logger.warning(
                    "[{}] Attempt {} failed: {} — retrying",
                    agent_name, attempt + 1, e,
                )
            else:
                logger.error("[{}] All {} attempts failed", agent_name, _MAX_RETRIES + 1)
    raise RuntimeError(f"[{agent_name}] Failed after {_MAX_RETRIES + 1} attempts: {last_error}")


async def async_run_chapter_pipeline(
    chapter_text: str,
    chapter_idx: int,
    book_slug: str,
    glossary: dict[str, Any] | None = None,
    verbose_mode: bool = False,
    toc: list[tuple[int, str, int]] | None = None,
    model: str | None = None,
) -> ChapterResult:
    """
    异步串联 4 个 Agent 处理单个章节。
    Writing + Exercise 在 Concept 完成后并行执行。

    Args/Returns: 同 run_chapter_pipeline
    """
    mode_label = "VERBOSE" if verbose_mode else "STANDARD"
    logger.info("=== Async pipeline started [{}]: {} Ch.{} (input: {} chars) ===", mode_label, book_slug, chapter_idx, len(chapter_text))
    pipeline_start = time.time()

    # Auto-upgrade: 当 section_splitter 检测到多个 section 时自动升级 verbose
    pre_sections: list | None = None
    if not verbose_mode:
        from src.section_splitter import split_chapter_into_sections
        pre_sections = split_chapter_into_sections(chapter_text, chapter_idx, toc)
        if len(pre_sections) > 1:
            verbose_mode = True
            logger.info(
                "Auto-upgraded to VERBOSE: chapter {} has {} sections from text headings",
                chapter_idx, len(pre_sections),
            )

    # Step 1: ConceptAgent
    step_start = time.time()
    concept_agent = ConceptAgent(model=model)
    concepts_result = await _async_run_with_retry(
        lambda: concept_agent.async_run(
            chapter_text=chapter_text,
            glossary=glossary,
            truncate=not verbose_mode,
        ),
        agent_name="ConceptAgent",
    )
    concepts_json = concepts_result.model_dump_json(indent=2)
    logger.info("Concepts: {} extracted ({:.1f}s)", len(concepts_result.concepts), time.time() - step_start)

    # Step 2+3: Writing + Exercise 并行
    parallel_start = time.time()
    writing_agent = WritingAgent(model=model)
    exercise_agent = ExerciseAgent(model=model)

    if verbose_mode:
        # Verbose: 写作保持串行（previous_summary 依赖），但与 Exercise 并行
        verbose_tuple, exercise_result = await asyncio.gather(
            _async_run_verbose_writing(
                writing_agent=writing_agent,
                chapter_text=chapter_text,
                chapter_idx=chapter_idx,
                concepts=concepts_json,
                toc=toc,
                pre_sections=pre_sections,
            ),
            _async_run_with_retry(
                lambda: exercise_agent.async_run(
                    chapter_text=chapter_text,
                    chapter_idx=chapter_idx,
                    concepts=concepts_json,
                ),
                agent_name="ExerciseAgent",
            ),
        )
        section_results_list, sections = verbose_tuple
        writing_result = _merge_verbose_sections(section_results_list)
    else:
        # Standard: Writing + Exercise 完全并行
        writing_result, exercise_result = await asyncio.gather(
            _async_run_with_retry(
                lambda: writing_agent.async_run(
                    chapter_text=chapter_text,
                    chapter_idx=chapter_idx,
                    concepts=concepts_json,
                ),
                agent_name="WritingAgent",
            ),
            _async_run_with_retry(
                lambda: exercise_agent.async_run(
                    chapter_text=chapter_text,
                    chapter_idx=chapter_idx,
                    concepts=concepts_json,
                ),
                agent_name="ExerciseAgent",
            ),
        )
        section_results_list = None
        sections = None

    logger.info("Writing: {} chars", len(writing_result))
    logger.info("Exercises: {} generated (parallel step {:.1f}s)", len(exercise_result.exercises), time.time() - parallel_start)

    # Step 4: TLDRAgent（依赖 writing output）
    step_start = time.time()
    tldr_agent = TLDRAgent(model=model)
    tldr_result = await _async_run_with_retry(
        lambda: tldr_agent.async_run(writing_output=writing_result, chapter_idx=chapter_idx),
        agent_name="TLDRAgent",
    )
    logger.info("TLDR: {} chars ({:.1f}s)", len(tldr_result), time.time() - step_start)

    # Step 5: 合并并写入文件（同步 I/O）
    output_dir = book_output_dir(book_slug)
    exercise_tldr_md = _build_exercise_tldr(exercise_result, tldr_result)

    if verbose_mode and section_results_list and len(section_results_list) > 1:
        section_paths = _write_multi_file(
            output_dir, chapter_idx, section_results_list, sections, exercise_tldr_md,
        )
        index_path = _write_chapter_index(
            output_dir, chapter_idx, sections, section_paths, exercise_tldr_md,
        )
        logger.info("=== Async pipeline completed: {} ({} sections, total {:.1f}s) ===", index_path, len(section_paths), time.time() - pipeline_start)
        return ChapterResult(
            output_path=index_path,
            concepts=concepts_result,
            section_paths=section_paths,
        )
    else:
        merged = _merge_outputs(writing_result, exercise_result, tldr_result, chapter_idx)
        filename = f"ch{chapter_idx:02d}.md"
        output_path = output_dir / filename
        _atomic_write(output_path, merged)
        logger.info("=== Async pipeline completed: {} (total {:.1f}s) ===", output_path, time.time() - pipeline_start)
        return ChapterResult(output_path=output_path, concepts=concepts_result)


async def _async_run_verbose_writing(
    writing_agent: WritingAgent,
    chapter_text: str,
    chapter_idx: int,
    concepts: str,
    toc: list[tuple[int, str, int]] | None,
    pre_sections: list | None = None,
) -> tuple[list[str], list]:
    """
    异步 Verbose 模式：逐节调用 WritingAgent（串行，previous_summary 依赖）。

    Returns:
        (section_results, sections) 元组
    """
    from src.section_splitter import split_chapter_into_sections

    if pre_sections is not None:
        sections = pre_sections
    else:
        sections = split_chapter_into_sections(chapter_text, chapter_idx, toc)
    logger.info(
        "Verbose mode: chapter {} split into {} sections",
        chapter_idx, len(sections),
    )

    section_results: list[str] = []
    previous_summary = ""

    for i, section in enumerate(sections):
        logger.info(
            "Verbose writing section {}/{} '{}' [L{}] ({} chars)",
            i + 1, len(sections), section.title[:50], section.depth, len(section.text),
        )
        result = await _async_run_with_retry(
            lambda s=section, idx=i: writing_agent.async_run_verbose(
                section_text=s.text,
                section_title=s.title,
                section_idx=idx,
                total_sections=len(sections),
                chapter_idx=chapter_idx,
                concepts=concepts,
                previous_summary=previous_summary,
            ),
            agent_name=f"WritingAgent/section-{i + 1}",
        )
        section_results.append(result)
        previous_summary = result[-500:] if len(result) > 500 else result

    return section_results, sections


def _run_verbose_writing(
    writing_agent: WritingAgent,
    chapter_text: str,
    chapter_idx: int,
    concepts: str,
    toc: list[tuple[int, str, int]] | None,
    pre_sections: list | None = None,
) -> tuple[list[str], list]:
    """
    Verbose 模式：自适应分节，逐节调用 WritingAgent 忠实改写。

    Returns:
        (section_results, sections) 元组：
        - section_results: 每节改写后的 Markdown 文本列表
        - sections: Section 对象列表（含标题等元数据）
    """
    from src.section_splitter import split_chapter_into_sections

    if pre_sections is not None:
        sections = pre_sections
    else:
        sections = split_chapter_into_sections(chapter_text, chapter_idx, toc)
    logger.info(
        "Verbose mode: chapter {} split into {} sections",
        chapter_idx, len(sections),
    )

    section_results: list[str] = []
    previous_summary = ""

    for i, section in enumerate(sections):
        logger.info(
            "Verbose writing section {}/{} '{}' [L{}] ({} chars)",
            i + 1, len(sections), section.title[:50], section.depth, len(section.text),
        )
        result = _run_with_retry(
            lambda s=section, idx=i: writing_agent.run_verbose(
                section_text=s.text,
                section_title=s.title,
                section_idx=idx,
                total_sections=len(sections),
                chapter_idx=chapter_idx,
                concepts=concepts,
                previous_summary=previous_summary,
            ),
            agent_name=f"WritingAgent/section-{i + 1}",
        )
        section_results.append(result)
        # 传递尾迹摘要给下一节
        previous_summary = result[-500:] if len(result) > 500 else result

    return section_results, sections


def _merge_verbose_sections(section_results: list[str]) -> str:
    """将各节改写结果合并为完整教程正文（供 Exercise/TLDR Agent 使用）。"""
    return "\n\n---\n\n".join(s.strip() for s in section_results)


def _build_exercise_tldr(exercises: ExerciseOutput, tldr: str) -> str:
    """构建练习题和要点提炼的 Markdown 块。"""
    parts: list[str] = []

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


def _write_multi_file(
    output_dir: Path,
    chapter_idx: int,
    section_results: list[str],
    sections: list,
    exercise_tldr_md: str,
) -> list[Path]:
    """
    Verbose 多文件输出：每节写一个 ch{NN}_{S}.md 文件。
    练习题和要点提炼附加在最后一节。

    Returns:
        分节文件路径列表
    """
    paths: list[Path] = []
    prefix = f"ch{chapter_idx:02d}"

    for i, (content, section) in enumerate(zip(section_results, sections)):
        filename = f"{prefix}_{i + 1}.md"
        path = output_dir / filename

        # 最后一节附加练习题和要点提炼
        if i == len(section_results) - 1:
            body = content.strip() + exercise_tldr_md
        else:
            body = content.strip()

        _atomic_write(path, body)
        paths.append(path)
        logger.info("Wrote section {}/{}: {} ({} chars)", i + 1, len(sections), filename, len(body))

    return paths


def _write_chapter_index(
    output_dir: Path,
    chapter_idx: int,
    sections: list,
    section_paths: list[Path],
    exercise_tldr_md: str,
) -> Path:
    """
    生成章节索引页 ch{NN}.md，包含各节链接。

    Returns:
        索引文件路径
    """
    prefix = f"ch{chapter_idx:02d}"
    index_path = output_dir / f"{prefix}.md"

    lines: list[str] = []
    lines.append(f"# 第 {chapter_idx} 章\n")
    lines.append(f"\n本章共 {len(sections)} 节，点击下方链接阅读：\n")

    for i, (section, path) in enumerate(zip(sections, section_paths)):
        lines.append(f"{i + 1}. [{section.title}]({path.name})\n")

    lines.append("\n---\n")

    index_path.write_text("\n".join(lines), encoding="utf-8")
    return index_path


def _merge_outputs(
    writing: str,
    exercises: ExerciseOutput,
    tldr: str,
    chapter_idx: int,
) -> str:
    """合并 4 个 Agent 的输出为最终 Markdown（标准单文件模式）。"""
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
        logger.debug("Atomic write: {} ({} chars)", path, len(content))
    except BaseException:
        if os.path.exists(tmp_path):
            os.unlink(tmp_path)
        logger.error("Atomic write failed for {}, temp file cleaned up", path)
        raise
