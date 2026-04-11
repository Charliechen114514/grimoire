"""Batch processing for full book tutorial generation."""
import argparse
import asyncio
import json
import logging
import sys
import time
from pathlib import Path
from typing import Any

from src.config import book_data_dir
from src.glossary import load_glossary, merge_concepts, save_glossary, trim_to_budget
from src.orchestrator import async_run_chapter_pipeline
from src.progress import init_progress, init_progress_fresh, mark_done, save_progress

logger = logging.getLogger(__name__)


def load_chapters_raw(book_slug: str) -> dict[str, Any]:
    """
    Load chapters_raw.json for the given book.

    Returns:
        The raw JSON dict (chapter keys are "1", "2", ..., plus "metadata")

    Raises:
        FileNotFoundError: if chapters_raw.json does not exist
    """
    path = book_data_dir(book_slug) / "chapters_raw.json"
    if not path.exists():
        raise FileNotFoundError(
            f"chapters_raw.json not found at {path}. "
            f"Run Phase 1 (pdf_parser.split_book) first."
        )
    data = json.loads(path.read_text(encoding="utf-8"))
    logger.info(
        "Loaded %s: %d chapters", path, data["metadata"]["total_chapters"],
    )
    return data


async def async_run_batch(
    book_slug: str,
    resume: bool = True,
    verbose_mode: bool = False,
    max_workers: int = 4,
    model: str | None = None,
) -> list[Path]:
    """
    异步批量处理所有章节，支持章节级并行。

    使用 asyncio.Semaphore 控制最大并发章节数。
    Glossary 采用快照策略：所有并行章节共享同一快照，完成后延迟合并。

    Args:
        book_slug: 书籍标识（如 "CSAPP"）
        resume: 是否跳过已完成的章节
        verbose_mode: 是否启用 verbose 模式
        max_workers: 最大并行章节数

    Returns:
        本次运行中处理的章节输出文件路径列表
    """
    raw = load_chapters_raw(book_slug)
    total_chapters = raw["metadata"]["total_chapters"]

    # 从 metadata 中加载 TOC（verbose 模式需要）
    toc_raw = raw["metadata"].get("toc")
    toc = None
    if toc_raw and verbose_mode:
        toc = [(e["level"], e["title"], e["page"]) for e in toc_raw]
        logger.info("Loaded TOC: %d entries for verbose mode", len(toc))
    elif verbose_mode and not toc_raw:
        logger.warning(
            "Verbose mode requested but no TOC in chapters_raw.json. "
            "Re-run 'parse' command to generate TOC data. "
            "Falling back to single-section mode.",
        )

    # Get sorted chapter keys (only numeric ones)
    chapter_keys = sorted(
        [k for k in raw.keys() if k.isdigit()],
        key=lambda k: int(k),
    )

    # Initialize progress
    if resume:
        progress = init_progress(book_slug, total_chapters)
    else:
        progress = init_progress_fresh(book_slug, total_chapters)
    save_progress(progress, book_slug)

    # Load existing glossary and snapshot
    glossary = load_glossary(book_slug)
    glossary_lock = asyncio.Lock()
    semaphore = asyncio.Semaphore(max_workers)

    completed: list[Path] = []
    completed_lock = asyncio.Lock()

    async def process_chapter(chapter_key: str) -> Path | None:
        """处理单个章节（带信号量控制并发）。"""
        chapter_idx = int(chapter_key)

        async with semaphore:
            # 再次检查状态（可能在等待信号量时已被其他任务处理）
            if resume and progress.get(chapter_key) == "done":
                logger.info("Skipping Ch.%d (already done)", chapter_idx)
                return None

            logger.info(
                "=== Processing Ch.%d/%d (%s) ===",
                chapter_idx, total_chapters, book_slug,
            )
            start_time = time.time()

            # 使用 glossary 快照
            trimmed = trim_to_budget(glossary) if glossary else None

            try:
                result = await async_run_chapter_pipeline(
                    chapter_text=raw[chapter_key],
                    chapter_idx=chapter_idx,
                    book_slug=book_slug,
                    glossary=trimmed,
                    verbose_mode=verbose_mode,
                    toc=toc,
                    model=model,
                )
            except Exception as e:
                logger.error("Ch.%d failed: %s", chapter_idx, e)
                progress[chapter_key] = "failed"
                save_progress(progress, book_slug)
                return None

            elapsed = time.time() - start_time
            logger.info(
                "Ch.%d done in %.1fs -> %s", chapter_idx, elapsed, result.output_path,
            )

            # 合并新概念到共享 glossary（锁保护）
            concept_dicts = [c.model_dump() for c in result.concepts.concepts]
            async with glossary_lock:
                glossary.update(merge_concepts(glossary, concept_dicts, chapter_idx))
                mark_done(progress, chapter_idx)
                save_progress(progress, book_slug)
                save_glossary(glossary, book_slug)

            async with completed_lock:
                completed.append(result.output_path)
            return result.output_path

    # 启动所有章节任务
    tasks = [process_chapter(k) for k in chapter_keys]
    await asyncio.gather(*tasks)

    logger.info(
        "=== Batch complete: %d/%d chapters processed ===",
        len(completed), total_chapters,
    )
    return completed


def run_batch(
    book_slug: str,
    resume: bool = True,
    verbose_mode: bool = False,
    max_workers: int = 1,
    model: str | None = None,
) -> list[Path]:
    """
    批量处理所有章节的同步入口。

    Args:
        book_slug: 书籍标识（如 "CSAPP"）
        resume: 是否跳过已完成的章节
        verbose_mode: 是否启用 verbose 模式
        max_workers: 最大并行章节数（默认 1 为串行）

    Returns:
        本次运行中处理的章节输出文件路径列表
    """
    return asyncio.run(async_run_batch(
        book_slug=book_slug,
        resume=resume,
        verbose_mode=verbose_mode,
        max_workers=max_workers,
        model=model,
    ))


def main() -> None:
    """CLI entry point."""
    parser = argparse.ArgumentParser(
        description="Batch process a book through the tutorial pipeline",
    )
    parser.add_argument(
        "book_slug",
        help="Book identifier (e.g., CSAPP)",
    )
    parser.add_argument(
        "--no-resume",
        action="store_true",
        help="Start from scratch, ignoring previous progress",
    )
    args = parser.parse_args()

    logging.basicConfig(
        level=logging.INFO,
        format="%(asctime)s [%(name)s] %(levelname)s: %(message)s",
    )

    try:
        paths = run_batch(
            book_slug=args.book_slug,
            resume=not args.no_resume,
        )
    except KeyboardInterrupt:
        logger.info("Interrupted — progress saved. Re-run to resume.")
        sys.exit(1)

    print(f"\nProcessed {len(paths)} chapters:")
    for p in paths:
        print(f"  {p}")


if __name__ == "__main__":
    main()
