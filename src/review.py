"""Review coordinator — 批量审核教程章节质量"""
import argparse
import json
import os
import sys
import tempfile
from concurrent.futures import ThreadPoolExecutor, as_completed
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
            result = agent.run(
                tutorial_markdown=tutorial_markdown,
                chapter_idx=chapter_idx,
                writing_style=writing_style,
            )
            result.chapter_idx = chapter_idx
            return result
        except (ValueError, Exception) as e:
            last_error = e
            if attempt < _MAX_RETRIES:
                logger.warning("Review Ch.{} attempt {} failed: {} — retrying", chapter_idx, attempt + 1, e)
            else:
                logger.error("Review Ch.{} failed after {} attempts", chapter_idx, _MAX_RETRIES + 1)

    raise RuntimeError(f"Review Ch.{chapter_idx} failed: {last_error}")


def _review_one(
    book_slug: str,
    chapter_idx: int,
    section_idx: int | None,
    label: str,
    writing_style: str,
) -> ChapterReview | None:
    """审核单个章节（线程安全，每次调用创建独立 Agent）。"""
    if section_idx is None:
        filename = f"ch{chapter_idx:02d}.md"
    else:
        filename = f"ch{chapter_idx:02d}_{section_idx}.md"

    tutorial_path = book_output_dir(book_slug) / filename
    if not tutorial_path.exists():
        logger.warning("{} tutorial not found, skipping", label)
        return None

    tutorial_markdown = tutorial_path.read_text(encoding="utf-8")
    logger.info("Reviewing {} ({})", label, book_slug)

    agent = ReviewAgent()
    last_error: Exception | None = None

    for attempt in range(_MAX_RETRIES + 1):
        try:
            result = agent.run(
                tutorial_markdown=tutorial_markdown,
                chapter_idx=chapter_idx,
                writing_style=writing_style,
                label=label,
            )
            result.chapter_idx = chapter_idx
            result.section_idx = section_idx
            return result
        except (ValueError, Exception) as e:
            last_error = e
            if attempt < _MAX_RETRIES:
                logger.warning("{} attempt {} failed: {} — retrying", label, attempt + 1, e)

    logger.error("{} failed: {}", label, last_error)
    return None


def review_book(
    book_slug: str,
    chapters: list[tuple[int, int | None]] | None = None,
    max_workers: int = 1,
) -> list[ChapterReview]:
    """
    批量审核教程章节，结果写入 data/{book_slug}/review_report.json。

    Args:
        book_slug: 书籍短名
        chapters: 指定审核的章节列表 [(chapter_idx, section_idx), ...]，
                  None 表示审核所有已生成的教程。
                  section_idx=None 表示无分节的主文件。
        max_workers: 最大并行章节数（默认 1 为串行）

    Returns:
        所有章节的 ChapterReview 列表
    """
    if chapters is None:
        chapters = _find_existing_chapters(book_slug)

    if not chapters:
        logger.warning("No chapters to review for {}", book_slug)
        return []

    writing_style = WRITING_STYLE_PATH.read_text(encoding="utf-8")

    # 构建任务列表
    tasks: list[tuple[int, int | None, str]] = []
    for chapter_idx, section_idx in chapters:
        if section_idx is None:
            label = f"Ch.{chapter_idx}"
        else:
            label = f"Ch.{chapter_idx}.{section_idx}"
        tasks.append((chapter_idx, section_idx, label))

    reviews: list[tuple[int, ChapterReview]] = []  # (order, review)

    if max_workers <= 1:
        # 串行执行
        for idx, (chapter_idx, section_idx, label) in enumerate(tasks):
            result = _review_one(book_slug, chapter_idx, section_idx, label, writing_style)
            if result is not None:
                reviews.append((idx, result))
    else:
        # 并行执行
        with ThreadPoolExecutor(max_workers=max_workers) as pool:
            futures = {}
            for idx, (chapter_idx, section_idx, label) in enumerate(tasks):
                future = pool.submit(
                    _review_one, book_slug, chapter_idx, section_idx, label, writing_style,
                )
                futures[future] = idx

            for future in as_completed(futures):
                result = future.result()
                if result is not None:
                    reviews.append((futures[future], result))

        # 按原始顺序排列
        reviews.sort(key=lambda x: x[0])

    ordered_reviews = [r for _, r in reviews]

    # 保存报告
    _save_report(ordered_reviews, book_slug)
    _print_summary(ordered_reviews, book_slug)

    return ordered_reviews


def review_and_fix(
    book_slug: str,
    chapters: list[tuple[int, int | None]] | None = None,
    max_workers: int = 1,
    max_fix_rounds: int = 2,
    model: str | None = None,
) -> list[ChapterReview]:
    """
    审核教程章节，对 FAIL 章节自动修复并重新审查。

    Args:
        book_slug: 书籍短名
        chapters: 指定审核的章节列表，None 表示全部
        max_workers: 最大并行数
        max_fix_rounds: 最大修复轮数（默认 2）
        model: 模型名称或 alias

    Returns:
        最终的 ChapterReview 列表（包含修复历史）
    """
    from src.agents.fix import FixAgent

    # Round 0: 初始审查
    logger.info("=== Review & Fix: {} (max_fix_rounds={}) ===", book_slug, max_fix_rounds)
    reviews = review_book(book_slug, chapters=chapters, max_workers=max_workers)

    if not reviews:
        return reviews

    # 为每个 review 初始化 fix_history
    fix_histories: dict[tuple[int, int | None], list[dict]] = {}
    for r in reviews:
        key = (r.chapter_idx, r.section_idx)
        fix_histories[key] = [
            _snapshot_scores(r, round_num=0),
        ]

    # 收集 FAIL 章节
    failed = [r for r in reviews if not r.overall_pass]
    if not failed:
        logger.info("All chapters PASS, no fix needed")
        return reviews

    logger.warning(
        "{}/{} chapters FAIL — auto-fix will start (max {} rounds)",
        len(failed), len(reviews), max_fix_rounds,
    )

    writing_style = WRITING_STYLE_PATH.read_text(encoding="utf-8")

    for fix_round in range(1, max_fix_rounds + 1):
        logger.info("=== Fix round {}/{}: {} chapters to fix ===", fix_round, max_fix_rounds, len(failed))

        # 并行修复
        fixed_results: dict[tuple[int, int | None], str | None] = {}

        def _fix_one(review: ChapterReview) -> tuple[tuple[int, int | None], str | None]:
            key = (review.chapter_idx, review.section_idx)
            if review.section_idx is None:
                label = f"Ch.{review.chapter_idx}"
                filename = f"ch{review.chapter_idx:02d}.md"
            else:
                label = f"Ch.{review.chapter_idx}.{review.section_idx}"
                filename = f"ch{review.chapter_idx:02d}_{review.section_idx}.md"

            tutorial_path = book_output_dir(book_slug) / filename
            tutorial_markdown = tutorial_path.read_text(encoding="utf-8")

            try:
                fix_agent = FixAgent(model=model)
                fixed_md = fix_agent.run(
                    tutorial_markdown=tutorial_markdown,
                    review=review,
                    writing_style=writing_style,
                    chapter_label=label,
                )
                # 原子写入修复后的文件
                _atomic_write_md(tutorial_path, fixed_md)
                logger.info("Fix {}: {} chars → {} chars", label, len(tutorial_markdown), len(fixed_md))
                return key, fixed_md
            except Exception as e:
                logger.error("Fix {} failed: {}", label, e)
                return key, None

        if max_workers <= 1:
            for review in failed:
                key, fixed_md = _fix_one(review)
                fixed_results[key] = fixed_md
        else:
            with ThreadPoolExecutor(max_workers=max_workers) as pool:
                futures = {pool.submit(_fix_one, r): r for r in failed}
                for future in as_completed(futures):
                    key, fixed_md = future.result()
                    fixed_results[key] = fixed_md

        # 只重审修复成功的章节
        re_review_chapters = []
        for review in failed:
            key = (review.chapter_idx, review.section_idx)
            if fixed_results.get(key) is not None:
                re_review_chapters.append((review.chapter_idx, review.section_idx))

        if not re_review_chapters:
            logger.warning("Fix round {}: all fixes failed", fix_round)
            break

        logger.info("Fix round {}: re-reviewing {} chapters", fix_round, len(re_review_chapters))

        # 重新审查
        new_reviews = _review_chapters(book_slug, re_review_chapters, writing_style, max_workers)

        # 更新 reviews 列表和 fix_histories
        new_review_map = {(r.chapter_idx, r.section_idx): r for r in new_reviews}
        updated_reviews: list[ChapterReview] = []

        for r in reviews:
            key = (r.chapter_idx, r.section_idx)
            if key in new_review_map:
                new_r = new_review_map[key]
                fix_histories[key].append(_snapshot_scores(new_r, round_num=fix_round))
                updated_reviews.append(new_r)
            else:
                updated_reviews.append(r)

        reviews = updated_reviews

        # 检查是否还有 FAIL
        failed = [r for r in reviews if not r.overall_pass]
        still_fail = len(failed)
        pass_count = len(reviews) - still_fail
        logger.info("After fix round {}: {} PASS, {} still FAIL", fix_round, pass_count, still_fail)

        if not failed:
            logger.info("All chapters PASS after fix round {}", fix_round)
            break

    # 保存最终报告（含修复历史）
    _save_report(reviews, book_slug, fix_histories=fix_histories)
    _print_summary(reviews, book_slug)

    return reviews


def _review_chapters(
    book_slug: str,
    chapters: list[tuple[int, int | None]],
    writing_style: str,
    max_workers: int = 1,
) -> list[ChapterReview]:
    """审查指定的章节列表（内部使用，不保存报告）。"""
    results: list[ChapterReview] = []

    def _do_review(chapter_idx: int, section_idx: int | None) -> ChapterReview | None:
        if section_idx is None:
            label = f"Ch.{chapter_idx}"
        else:
            label = f"Ch.{chapter_idx}.{section_idx}"
        return _review_one(book_slug, chapter_idx, section_idx, label, writing_style)

    if max_workers <= 1:
        for chapter_idx, section_idx in chapters:
            result = _do_review(chapter_idx, section_idx)
            if result is not None:
                results.append(result)
    else:
        with ThreadPoolExecutor(max_workers=max_workers) as pool:
            futures = {pool.submit(_do_review, ci, si): (ci, si) for ci, si in chapters}
            for future in as_completed(futures):
                result = future.result()
                if result is not None:
                    results.append(result)

    return results


def _snapshot_scores(review: ChapterReview, round_num: int) -> dict:
    """生成单轮审查快照。"""
    return {
        "round": round_num,
        "scores": {s.dimension: s.score for s in review.scores},
        "overall_pass": review.overall_pass,
    }


def _atomic_write_md(path: Path, content: str) -> None:
    """原子写入 Markdown 文件。"""
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


def _find_existing_chapters(book_slug: str) -> list[tuple[int, int | None]]:
    """
    扫描 tutorials 目录，返回所有可审核的教程文件。

    Returns:
        [(chapter_idx, section_idx), ...] 列表。
        - 无分节章节：(5, None) → 审核文件 ch05.md
        - 有分节章节：(3, 1) → 审核文件 ch03_1.md
    """
    tutorials_dir = book_output_dir(book_slug)
    files = sorted(tutorials_dir.glob("ch*.md"))

    # 先收集哪些主章节有分节文件
    chapters_with_sections: set[int] = set()
    for path in files:
        stem = path.stem
        if "_" not in stem:
            continue
        parts = stem.split("_", 1)
        try:
            ch_num = int(parts[0][2:])
            int(parts[1])  # section number
            chapters_with_sections.add(ch_num)
        except ValueError:
            continue

    result: list[tuple[int, int | None]] = []
    for path in files:
        stem = path.stem
        if "_" in stem:
            # 分节文件：ch03_1.md → (3, 1)
            parts = stem.split("_", 1)
            try:
                ch_num = int(parts[0][2:])
                sec_num = int(parts[1])
                result.append((ch_num, sec_num))
            except ValueError:
                continue
        else:
            # 主文件：ch05.md → (5, None)，但跳过仅作索引的主文件
            try:
                ch_num = int(stem[2:])
            except ValueError:
                continue
            if ch_num in chapters_with_sections:
                continue  # 有分节时，主文件只是索引
            result.append((ch_num, None))

    return result


def _save_report(
    reviews: list[ChapterReview],
    book_slug: str,
    *,
    fix_histories: dict[tuple[int, int | None], list[dict]] | None = None,
) -> None:
    """原子写入 review_report.json。"""
    data_dir = book_data_dir(book_slug)
    report_path = data_dir / "review_report.json"

    # 计算总修复轮数
    total_fix_rounds = 0
    if fix_histories:
        for history in fix_histories.values():
            rounds = len(history) - 1  # 减去 round 0（初始审查）
            total_fix_rounds = max(total_fix_rounds, rounds)

    report_data = {
        "book_slug": book_slug,
        "total_reviewed": len(reviews),
        "fix_rounds": total_fix_rounds if total_fix_rounds > 0 else None,
        "chapters": [
            _build_chapter_report(r, fix_histories)
            for r in reviews
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


def _build_chapter_report(
    review: ChapterReview,
    fix_histories: dict[tuple[int, int | None], list[dict]] | None,
) -> dict:
    """构建单个章节的报告数据。"""
    key = (review.chapter_idx, review.section_idx)
    entry: dict = {
        "chapter_idx": review.chapter_idx,
        "section_idx": review.section_idx,
        "scores": [
            {"dimension": s.dimension, "score": s.score, "rationale": s.rationale}
            for s in review.scores
        ],
        "issues": [issue.model_dump() for issue in review.issues],
        "overall_pass": review.overall_pass,
    }
    if fix_histories and key in fix_histories and len(fix_histories[key]) > 1:
        entry["fix_history"] = fix_histories[key]
    return entry


def _print_summary(reviews: list[ChapterReview], book_slug: str) -> None:
    """打印审核摘要到 stdout。"""
    print(f"\n{'='*60}")
    print(f"Review Summary: {book_slug}")
    print(f"{'='*60}")

    for review in reviews:
        status = "PASS" if review.overall_pass else "FAIL"
        scores_str = ", ".join(f"{s.dimension}={s.score}" for s in review.scores)
        label = f"Ch.{review.chapter_idx}" if review.section_idx is None else f"Ch.{review.chapter_idx}.{review.section_idx}"
        print(f"  {label}: [{status}] {scores_str}")

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

    chapters = [(c, None) for c in args.chapters] if args.chapters else None

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
