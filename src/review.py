"""Review coordinator — 批量审核教程章节质量"""
import argparse
import json
import os
import sys
import tempfile
from pathlib import Path

from src.agents.review import ChapterReview, ReviewAgent
from src.config import WRITING_STYLE_PATH, book_data_dir, book_output_dir
from src.log import logger

_MAX_RETRIES = 2


def review_chapter(book_slug: str, chapter_idx: int) -> ChapterReview:
    """
    审核单个已生成的教程章节。

    Args:
        book_slug: 书籍短名
        chapter_idx: 章节编号（1-indexed）

    Returns:
        ChapterReview 审核结果

    Raises:
        FileNotFoundError: 教程文件不存在
        RuntimeError: Agent 执行失败
    """
    tutorial_path = book_output_dir(book_slug) / f"ch{chapter_idx:02d}.md"
    if not tutorial_path.exists():
        raise FileNotFoundError(f"Tutorial not found: {tutorial_path}")

    tutorial_markdown = tutorial_path.read_text(encoding="utf-8")
    writing_style = WRITING_STYLE_PATH.read_text(encoding="utf-8")

    agent = ReviewAgent()
    last_error: Exception | None = None

    for attempt in range(_MAX_RETRIES + 1):
        try:
            return agent.run(
                tutorial_markdown=tutorial_markdown,
                chapter_idx=chapter_idx,
                writing_style=writing_style,
            )
        except (ValueError, Exception) as e:
            last_error = e
            if attempt < _MAX_RETRIES:
                logger.warning("Review Ch.{} attempt {} failed: {} — retrying", chapter_idx, attempt + 1, e)
            else:
                logger.error("Review Ch.{} failed after {} attempts", chapter_idx, _MAX_RETRIES + 1)

    raise RuntimeError(f"Review Ch.{chapter_idx} failed: {last_error}")


def review_book(
    book_slug: str,
    chapters: list[int] | None = None,
) -> list[ChapterReview]:
    """
    批量审核教程章节，结果写入 data/{book_slug}/review_report.json。

    Args:
        book_slug: 书籍短名
        chapters: 指定审核的章节列表，None 表示审核所有已生成的教程

    Returns:
        所有章节的 ChapterReview 列表
    """
    if chapters is None:
        chapters = _find_existing_chapters(book_slug)

    if not chapters:
        logger.warning("No chapters to review for {}", book_slug)
        return []

    writing_style = WRITING_STYLE_PATH.read_text(encoding="utf-8")
    agent = ReviewAgent()
    reviews: list[ChapterReview] = []

    for chapter_idx in chapters:
        tutorial_path = book_output_dir(book_slug) / f"ch{chapter_idx:02d}.md"
        if not tutorial_path.exists():
            logger.warning("Ch.{} tutorial not found, skipping", chapter_idx)
            continue

        tutorial_markdown = tutorial_path.read_text(encoding="utf-8")
        logger.info("Reviewing Ch.{}/{} ({})", chapter_idx, len(chapters), book_slug)

        result: ChapterReview | None = None
        last_error: Exception | None = None

        for attempt in range(_MAX_RETRIES + 1):
            try:
                result = agent.run(
                    tutorial_markdown=tutorial_markdown,
                    chapter_idx=chapter_idx,
                    writing_style=writing_style,
                )
                break
            except (ValueError, Exception) as e:
                last_error = e
                if attempt < _MAX_RETRIES:
                    logger.warning("Review Ch.{} attempt {} failed: {} — retrying", chapter_idx, attempt + 1, e)

        if result is None:
            logger.error("Review Ch.{} failed: {}", chapter_idx, last_error)
            continue

        reviews.append(result)

    # 保存报告
    _save_report(reviews, book_slug)
    _print_summary(reviews, book_slug)

    return reviews


def _find_existing_chapters(book_slug: str) -> list[int]:
    """扫描 tutorials 目录，返回所有已生成教程的章节编号。"""
    tutorials_dir = book_output_dir(book_slug)
    chapters: list[int] = []
    for path in sorted(tutorials_dir.glob("ch*.md")):
        # ch01.md -> 1, ch12.md -> 12
        try:
            num = int(path.stem[2:])
            chapters.append(num)
        except ValueError:
            continue
    return chapters


def _save_report(reviews: list[ChapterReview], book_slug: str) -> None:
    """原子写入 review_report.json。"""
    data_dir = book_data_dir(book_slug)
    report_path = data_dir / "review_report.json"

    report_data = {
        "book_slug": book_slug,
        "total_reviewed": len(reviews),
        "chapters": [
            {
                "chapter_idx": i + 1,
                "scores": [{"dimension": s.dimension, "score": s.score, "rationale": s.rationale} for s in r.scores],
                "issues": [issue.model_dump() for issue in r.issues],
                "overall_pass": r.overall_pass,
            }
            for i, r in enumerate(reviews)
        ],
    }

    fd, tmp_path = tempfile.mkstemp(suffix=".json", dir=str(data_dir))
    try:
        with os.fdopen(fd, "w", encoding="utf-8") as f:
            json.dump(report_data, f, ensure_ascii=False, indent=2)
        os.replace(tmp_path, report_path)
    except BaseException:
        if os.path.exists(tmp_path):
            os.unlink(tmp_path)
        raise

    logger.info("Review report saved: {}", report_path)


def _print_summary(reviews: list[ChapterReview], book_slug: str) -> None:
    """打印审核摘要到 stdout。"""
    print(f"\n{'='*60}")
    print(f"Review Summary: {book_slug}")
    print(f"{'='*60}")

    for i, review in enumerate(reviews):
        status = "PASS" if review.overall_pass else "FAIL"
        scores_str = ", ".join(f"{s.dimension}={s.score}" for s in review.scores)
        print(f"  Ch.{i+1}: [{status}] {scores_str}")

        for issue in review.issues:
            if issue.severity == "high":
                print(f"    ⚠️  [{issue.severity}] {issue.dimension}: {issue.issue} ({issue.location})")

    total_issues = sum(len(r.issues) for r in reviews)
    high_count = sum(1 for r in reviews for issue in r.issues if issue.severity == "high")
    pass_count = sum(1 for r in reviews if r.overall_pass)

    print(f"\n  Total: {len(reviews)} chapters, {pass_count} passed, {total_issues} issues ({high_count} high)")
    print(f"{'='*60}\n")


def main() -> None:
    """CLI entry point."""
    parser = argparse.ArgumentParser(description="Review generated tutorials")
    parser.add_argument("book_slug", help="Book identifier (e.g., CSAPP)")
    parser.add_argument(
        "--chapters",
        nargs="+",
        type=int,
        help="Specific chapters to review",
    )
    parser.add_argument(
        "--all",
        action="store_true",
        help="Review all existing tutorials",
    )
    args = parser.parse_args()

    from src.log import setup_logging
    setup_logging(verbose=False)

    chapters = args.chapters if args.chapters else None

    try:
        reviews = review_book(
            book_slug=args.book_slug,
            chapters=chapters,
        )
    except KeyboardInterrupt:
        logger.info("Interrupted.")
        sys.exit(1)

    if not reviews:
        print("No chapters reviewed.")
        sys.exit(1)


if __name__ == "__main__":
    main()
