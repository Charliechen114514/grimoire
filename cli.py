"""Tutorial Summon — unified CLI entry point.

Usage:
    python -m cli parse   books/book.pdf --slug MYBOOK
    python -m cli parse   https://www.wolai.com/xxx --slug MYBOOK
    python -m cli parse   https://example.com/tutorial --slug MYTUTORIAL --engine static
    python -m cli batch   MYBOOK [--no-resume]
    python -m cli review  MYBOOK [--chapters 1 2 3]
    python -m cli package MYBOOK [--site-name "My Book"]
    python -m cli all     books/book.pdf --slug MYBOOK [--site-name "My Book"]
"""
import argparse
import os
import sys
from pathlib import Path

from dotenv import load_dotenv

load_dotenv()  # 确保在读取环境变量之前加载 .env

from src.log import setup_logging

# 环境变量默认值（必须在 load_dotenv 之后）
_VERBOSE_MODE_DEFAULT = os.getenv("VERBOSE_MODE", "").lower() in ("1", "true", "yes")


def _build_web_kwargs(args: argparse.Namespace) -> dict:
    """从 CLI 参数构建 Web 引擎配置。"""
    kwargs = {}
    if getattr(args, "selector", None):
        kwargs["selector"] = args.selector
    if getattr(args, "nav_selector", None):
        kwargs["nav_selector"] = args.nav_selector
    if getattr(args, "url_pattern", None):
        kwargs["url_pattern"] = args.url_pattern
    return kwargs


def _cmd_parse(args: argparse.Namespace) -> None:
    from src.parsers import get_parser, save_chapters_raw

    setup_logging(args.verbose)

    source = args.source
    slug = args.slug
    kwargs = _build_web_kwargs(args)

    try:
        parser = get_parser(
            source,
            source_type=getattr(args, "source_type", None),
            engine=getattr(args, "engine", None),
            extract_images=not getattr(args, "no_images", False),
            **kwargs,
        )
        result = parser.parse(source, slug)
    except FileNotFoundError as e:
        print(f"Error: {e}", file=sys.stderr)
        sys.exit(1)
    except ValueError as e:
        print(f"Error: {e}", file=sys.stderr)
        sys.exit(1)
    except RuntimeError as e:
        print(f"Error: {e}", file=sys.stderr)
        sys.exit(1)

    if not result.chapters:
        print("Error: no chapters extracted from source", file=sys.stderr)
        sys.exit(1)

    out = save_chapters_raw(result, slug)
    print(f"OK: {result.metadata.total_chapters} chapters -> {out}")


def _cmd_batch(args: argparse.Namespace) -> None:
    from src.batch import run_batch

    setup_logging(args.verbose)
    try:
        paths = run_batch(
            book_slug=args.book_slug,
            resume=not args.no_resume,
            verbose_mode=getattr(args, "verbose_mode", False),
            max_workers=getattr(args, "workers", 1),
            model=getattr(args, "model", None),
        )
    except FileNotFoundError as e:
        print(f"Error: {e}", file=sys.stderr)
        print(f"Hint: run 'parse' command first to generate chapters_raw.json.", file=sys.stderr)
        sys.exit(1)
    except KeyboardInterrupt:
        print("Interrupted — progress saved. Re-run to resume.")
        sys.exit(1)

    print(f"\nProcessed {len(paths)} chapters:")
    for p in paths:
        print(f"  {p}")


def _cmd_review(args: argparse.Namespace) -> None:
    from src.review import review_book

    setup_logging(args.verbose)
    chapters = args.chapters if args.chapters else None

    try:
        reviews = review_book(book_slug=args.book_slug, chapters=chapters)
    except FileNotFoundError as e:
        print(f"Error: {e}", file=sys.stderr)
        print(f"Hint: run 'python -m cli batch {args.book_slug}' first to generate tutorials.", file=sys.stderr)
        sys.exit(1)
    except KeyboardInterrupt:
        print("Interrupted.")
        sys.exit(1)

    if not reviews:
        print("No chapters reviewed.")
        sys.exit(1)


def _cmd_package(args: argparse.Namespace) -> None:
    from src.packager import package

    setup_logging(args.verbose)
    try:
        config_path = package(args.book_slug, site_name=args.site_name)
    except FileNotFoundError as e:
        print(f"Error: {e}", file=sys.stderr)
        print(f"Hint: run 'python -m cli batch {args.book_slug}' first to generate tutorials.", file=sys.stderr)
        sys.exit(1)
    print(f"\nGenerated mkdocs config: {config_path}")
    print(f"Run: cd {config_path.parent} && mkdocs serve")


def _cmd_all(args: argparse.Namespace) -> None:
    """Run the full pipeline: parse → batch → review → package."""
    from src.batch import run_batch
    from src.packager import package
    from src.parsers import get_parser, save_chapters_raw
    from src.review import review_book

    setup_logging(args.verbose)

    source = args.source
    slug = args.slug

    # Phase 1: Parse
    print(f"\n{'='*60}")
    print(f"[1/4] Parsing source: {source}")
    print(f"{'='*60}")

    try:
        kwargs = _build_web_kwargs(args)
        parser = get_parser(
            source,
            engine=getattr(args, "engine", None),
            extract_images=not getattr(args, "no_images", False),
            **kwargs,
        )
        result = parser.parse(source, slug)
    except (FileNotFoundError, ValueError, RuntimeError) as e:
        print(f"Error: {e}", file=sys.stderr)
        sys.exit(1)

    if not result.chapters:
        print("Error: no chapters extracted from source", file=sys.stderr)
        sys.exit(1)

    save_chapters_raw(result, slug)
    print(f"  Parsed {result.metadata.total_chapters} chapters")

    # Phase 2: Batch generate tutorials
    print(f"\n{'='*60}")
    print(f"[2/4] Generating tutorials for: {slug}")
    print(f"{'='*60}")
    try:
        run_batch(
            book_slug=slug,
            resume=not args.no_resume,
            verbose_mode=getattr(args, "verbose_mode", False),
            max_workers=getattr(args, "workers", 1),
            model=getattr(args, "model", None),
        )
    except KeyboardInterrupt:
        print("Interrupted — progress saved. Re-run with 'batch' to resume.")
        sys.exit(1)

    # Phase 3: Review
    print(f"\n{'='*60}")
    print(f"[3/4] Reviewing tutorials for: {slug}")
    print(f"{'='*60}")
    review_book(book_slug=slug)

    # Phase 4: Package
    print(f"\n{'='*60}")
    print(f"[4/4] Packaging mkdocs site for: {slug}")
    print(f"{'='*60}")
    config_path = package(slug, site_name=args.site_name)

    print(f"\n{'='*60}")
    print(f"Pipeline complete! mkdocs config: {config_path}")
    print(f"Run: cd {config_path.parent} && mkdocs serve")
    print(f"{'='*60}")


def main() -> None:
    parser = argparse.ArgumentParser(
        prog="summon",
        description="Tutorial Summon — content to tutorial pipeline (PDF, web, etc.)",
    )
    parser.add_argument("-v", "--verbose", action="store_true", help="Debug logging")
    sub = parser.add_subparsers(dest="command", required=True)

    # ── parse ──
    p_parse = sub.add_parser("parse", help="Parse source into per-chapter text")
    p_parse.add_argument("source", help="Path to PDF file or URL of tutorial website")
    p_parse.add_argument("--slug", "-s", required=True, help="Book slug (e.g. MYBOOK)")
    p_parse.add_argument(
        "--source-type", "-t", default=None,
        choices=["pdf", "web"],
        help="Force source type (auto-detected if omitted)",
    )
    p_parse.add_argument(
        "--engine", "-e", default=None,
        help="Web engine: wolai, static, playwright, or path/to/custom.py (auto-detected if omitted)",
    )
    p_parse.add_argument(
        "--selector", default=None,
        help="CSS selector for content area (web source)",
    )
    p_parse.add_argument(
        "--nav-selector", default=None,
        help="CSS selector for navigation links (web source)",
    )
    p_parse.add_argument(
        "--url-pattern", default=None,
        help="Regex pattern for chapter URLs (web source, e.g. '/chapter-\\d+')",
    )
    p_parse.add_argument(
        "--no-images", action="store_true",
        help="Skip image extraction from PDF (text only)",
    )

    # ── batch ──
    p_batch = sub.add_parser("batch", help="Run full tutorial generation pipeline")
    p_batch.add_argument("book_slug", help="Book identifier")
    p_batch.add_argument("--no-resume", action="store_true", help="Start from scratch")
    p_batch.add_argument(
        "--verbose-mode", action="store_true", default=_VERBOSE_MODE_DEFAULT,
        help="Verbose mode: section-by-section faithful rewrite (env: VERBOSE_MODE)",
    )
    p_batch.add_argument(
        "--workers", "-w", type=int, default=1,
        help="Max concurrent chapters (default: 1 = sequential)",
    )
    p_batch.add_argument(
        "--model", "-m", default=None,
        help="Model alias (haiku/sonnet/opus) or full model name (default: sonnet)",
    )

    # ── review ──
    p_review = sub.add_parser("review", help="Review generated tutorials")
    p_review.add_argument("book_slug", help="Book identifier")
    p_review.add_argument("--chapters", nargs="+", type=int, help="Specific chapters")

    # ── package ──
    p_pkg = sub.add_parser("package", help="Package tutorials as mkdocs site")
    p_pkg.add_argument("book_slug", help="Book identifier")
    p_pkg.add_argument("--site-name", default=None, help="Site display name")

    # ── all ──
    p_all = sub.add_parser("all", help="Full pipeline: parse → batch → review → package")
    p_all.add_argument("source", help="Path to PDF file or URL of tutorial website")
    p_all.add_argument("--slug", "-s", required=True, help="Book slug")
    p_all.add_argument("--site-name", default=None, help="Site display name")
    p_all.add_argument("--no-resume", action="store_true", help="Start batch from scratch")
    p_all.add_argument(
        "--engine", "-e", default=None,
        help="Web engine: wolai, static, playwright, or path/to/custom.py",
    )
    p_all.add_argument(
        "--verbose-mode", action="store_true", default=_VERBOSE_MODE_DEFAULT,
        help="Verbose mode: section-by-section faithful rewrite (env: VERBOSE_MODE)",
    )
    p_all.add_argument(
        "--workers", "-w", type=int, default=1,
        help="Max concurrent chapters (default: 1 = sequential)",
    )
    p_all.add_argument(
        "--model", "-m", default=None,
        help="Model alias (haiku/sonnet/opus) or full model name (default: sonnet)",
    )
    p_all.add_argument(
        "--selector", default=None,
        help="CSS selector for content area (web source)",
    )
    p_all.add_argument(
        "--no-images", action="store_true",
        help="Skip image extraction from PDF (text only)",
    )

    args = parser.parse_args()

    dispatch = {
        "parse": _cmd_parse,
        "batch": _cmd_batch,
        "review": _cmd_review,
        "package": _cmd_package,
        "all": _cmd_all,
    }
    dispatch[args.command](args)


if __name__ == "__main__":
    main()
