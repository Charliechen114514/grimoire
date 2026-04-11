"""Batch processing for full book tutorial generation."""
import argparse
import json
import logging
import sys
import time
from pathlib import Path
from typing import Any

from src.config import book_data_dir
from src.glossary import load_glossary, merge_concepts, save_glossary, trim_to_budget
from src.orchestrator import run_chapter_pipeline
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


def run_batch(
    book_slug: str,
    resume: bool = True,
) -> list[Path]:
    """
    Process all chapters of a book through the pipeline.

    For each chapter:
    1. Skip if already done (when resume=True)
    2. Load glossary, trim to budget, pass to pipeline
    3. Merge new concepts back into glossary
    4. Save progress and glossary immediately (breakpoint-safe)

    Args:
        book_slug: Book identifier (e.g., "CSAPP")
        resume: If True, skip chapters already marked "done"

    Returns:
        List of output file paths for all chapters processed in this run
    """
    raw = load_chapters_raw(book_slug)
    total_chapters = raw["metadata"]["total_chapters"]

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

    # Load existing glossary
    glossary = load_glossary(book_slug)

    completed: list[Path] = []

    for chapter_key in chapter_keys:
        chapter_idx = int(chapter_key)
        status = progress.get(chapter_key, "pending")

        if resume and status == "done":
            logger.info("Skipping Ch.%d (already done)", chapter_idx)
            continue

        logger.info(
            "=== Processing Ch.%d/%d (%s) ===",
            chapter_idx, total_chapters, book_slug,
        )
        start_time = time.time()

        # Trim glossary before passing to pipeline
        trimmed = trim_to_budget(glossary) if glossary else None

        try:
            result = run_chapter_pipeline(
                chapter_text=raw[chapter_key],
                chapter_idx=chapter_idx,
                book_slug=book_slug,
                glossary=trimmed,
            )
        except RuntimeError as e:
            logger.error("Ch.%d failed: %s", chapter_idx, e)
            progress[chapter_key] = "failed"
            save_progress(progress, book_slug)
            raise

        elapsed = time.time() - start_time
        logger.info(
            "Ch.%d done in %.1fs -> %s", chapter_idx, elapsed, result.output_path,
        )

        # Merge new concepts into glossary
        concept_dicts = [c.model_dump() for c in result.concepts.concepts]
        glossary = merge_concepts(glossary, concept_dicts, chapter_idx)

        # Save both progress and glossary immediately (breakpoint-safe)
        mark_done(progress, chapter_idx)
        save_progress(progress, book_slug)
        save_glossary(glossary, book_slug)

        completed.append(result.output_path)

    logger.info(
        "=== Batch complete: %d/%d chapters processed ===",
        len(completed), total_chapters,
    )
    return completed


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
