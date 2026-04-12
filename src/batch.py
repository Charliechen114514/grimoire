"""Batch processing for full book tutorial generation."""
import argparse
import asyncio
import json
import sys
import time
from pathlib import Path
from typing import Any

from src.config import book_data_dir
from src.glossary import load_glossary, merge_concepts, save_glossary, trim_to_budget
from src.log import logger
from src.orchestrator import async_run_chapter_pipeline
from src.parsers import load_chapters_raw
from src.progress import init_progress, init_progress_fresh, mark_done, save_progress


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
    metadata = raw.metadata
    total_chapters = metadata.total_chapters
    batch_start = time.time()
    logger.info(
        "Batch starting: book={}, chapters={}, workers={}, verbose={}, resume={}, model={}, source={}",
        book_slug, total_chapters, max_workers, verbose_mode, resume, model, metadata.source_type,
    )

    # 从 metadata 中加载 TOC（verbose 模式和 auto-upgrade 都需要）
    toc = None
    if metadata.toc:
        toc = [(e.level, e.title, 0) for e in metadata.toc]
        logger.info("Loaded TOC: {} entries", len(toc))
    elif verbose_mode:
        logger.warning(
            "Verbose mode requested but no TOC in chapters_raw.json. "
            "Falling back to single-section mode.",
        )

    # Get sorted chapter keys (only numeric ones)
    chapter_keys = sorted(
        [k for k in raw.chapters.keys() if k.isdigit()],
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
    logger.info("Loaded glossary: {} concepts", len(glossary))
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
                logger.info("Skipping Ch.{} (already done)", chapter_idx)
                return None

            logger.info(
                "=== Processing Ch.{}/{} ({}) ===",
                chapter_idx, total_chapters, book_slug,
            )
            start_time = time.time()

            # 使用 glossary 快照
            trimmed = trim_to_budget(glossary) if glossary else None

            try:
                result = await async_run_chapter_pipeline(
                    chapter_text=raw.chapters[chapter_key],
                    chapter_idx=chapter_idx,
                    book_slug=book_slug,
                    glossary=trimmed,
                    verbose_mode=verbose_mode,
                    toc=toc,
                    model=model,
                )
            except Exception as e:
                logger.error("Ch.{} failed after {:.1f}s: {}", chapter_idx, time.time() - start_time, e)
                progress[chapter_key] = "failed"
                save_progress(progress, book_slug)
                return None

            elapsed = time.time() - start_time
            logger.info(
                "Ch.{} done in {:.1f}s -> {}", chapter_idx, elapsed, result.output_path,
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
        "=== Batch complete: {}/{} chapters processed ({:.1f}s) ===",
        len(completed), total_chapters, time.time() - batch_start,
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

    from src.log import setup_logging
    setup_logging(verbose=False)

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
