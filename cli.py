"""Tutorial Summon — unified CLI entry point.

Usage:
    python -m cli parse   books/book.pdf --slug MYBOOK
    python -m cli batch   MYBOOK [--no-resume]
    python -m cli review  MYBOOK [--chapters 1 2 3]
    python -m cli package MYBOOK [--site-name "My Book"]
    python -m cli all     books/book.pdf --slug MYBOOK [--site-name "My Book"]
"""
import argparse
import logging
import sys
from pathlib import Path


def _setup_logging(verbose: bool) -> None:
    logging.basicConfig(
        level=logging.DEBUG if verbose else logging.INFO,
        format="%(asctime)s [%(name)s] %(levelname)s: %(message)s",
    )


def _cmd_parse(args: argparse.Namespace) -> None:
    from src.pdf_parser import save_chapters_raw, split_book

    _setup_logging(args.verbose)
    pdf_path = Path(args.pdf)
    if not pdf_path.exists():
        print(f"Error: file not found: {pdf_path}", file=sys.stderr)
        sys.exit(1)

    chapters, toc = split_book(pdf_path, book_slug=args.slug)
    if not chapters:
        print("Error: no chapters found in PDF TOC", file=sys.stderr)
        sys.exit(1)

    out = save_chapters_raw(chapters, book_slug=args.slug, pdf_path=pdf_path, toc=toc)
    print(f"OK: {len(chapters)} chapters -> {out}")


def _cmd_batch(args: argparse.Namespace) -> None:
    from src.batch import run_batch

    _setup_logging(args.verbose)
    try:
        paths = run_batch(
            book_slug=args.book_slug,
            resume=not args.no_resume,
            verbose_mode=getattr(args, "verbose_mode", False),
            max_workers=getattr(args, "workers", 1),
            model=getattr(args, "model", None),
        )
    except KeyboardInterrupt:
        print("Interrupted — progress saved. Re-run to resume.")
        sys.exit(1)

    print(f"\nProcessed {len(paths)} chapters:")
    for p in paths:
        print(f"  {p}")


def _cmd_review(args: argparse.Namespace) -> None:
    from src.review import review_book

    _setup_logging(args.verbose)
    chapters = args.chapters if args.chapters else None

    try:
        reviews = review_book(book_slug=args.book_slug, chapters=chapters)
    except KeyboardInterrupt:
        print("Interrupted.")
        sys.exit(1)

    if not reviews:
        print("No chapters reviewed.")
        sys.exit(1)


def _cmd_package(args: argparse.Namespace) -> None:
    from src.packager import package

    _setup_logging(args.verbose)
    config_path = package(args.book_slug, site_name=args.site_name)
    print(f"\nGenerated mkdocs config: {config_path}")
    print(f"Run: cd {config_path.parent} && mkdocs serve")


def _cmd_all(args: argparse.Namespace) -> None:
    """Run the full pipeline: parse → batch → review → package."""
    from src.batch import run_batch
    from src.packager import package
    from src.pdf_parser import save_chapters_raw, split_book
    from src.review import review_book

    _setup_logging(args.verbose)

    pdf_path = Path(args.pdf)
    slug = args.slug

    # Phase 1: Parse
    print(f"\n{'='*60}")
    print(f"[1/4] Parsing PDF: {pdf_path}")
    print(f"{'='*60}")
    if not pdf_path.exists():
        print(f"Error: file not found: {pdf_path}", file=sys.stderr)
        sys.exit(1)

    chapters, toc = split_book(pdf_path, book_slug=slug)
    if not chapters:
        print("Error: no chapters found in PDF TOC", file=sys.stderr)
        sys.exit(1)
    save_chapters_raw(chapters, book_slug=slug, pdf_path=pdf_path, toc=toc)
    print(f"  Parsed {len(chapters)} chapters")

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
        description="Tutorial Summon — PDF textbook to tutorial pipeline",
    )
    parser.add_argument("-v", "--verbose", action="store_true", help="Debug logging")
    sub = parser.add_subparsers(dest="command", required=True)

    # ── parse ──
    p_parse = sub.add_parser("parse", help="Parse PDF into per-chapter text")
    p_parse.add_argument("pdf", help="Path to the PDF file")
    p_parse.add_argument("--slug", "-s", required=True, help="Book slug (e.g. MYBOOK)")

    # ── batch ──
    p_batch = sub.add_parser("batch", help="Run full tutorial generation pipeline")
    p_batch.add_argument("book_slug", help="Book identifier")
    p_batch.add_argument("--no-resume", action="store_true", help="Start from scratch")
    p_batch.add_argument(
        "--verbose-mode", action="store_true",
        help="Verbose mode: section-by-section faithful rewrite",
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
    p_all.add_argument("pdf", help="Path to the PDF file")
    p_all.add_argument("--slug", "-s", required=True, help="Book slug")
    p_all.add_argument("--site-name", default=None, help="Site display name")
    p_all.add_argument("--no-resume", action="store_true", help="Start batch from scratch")
    p_all.add_argument(
        "--verbose-mode", action="store_true",
        help="Verbose mode: section-by-section faithful rewrite",
    )
    p_all.add_argument(
        "--workers", "-w", type=int, default=1,
        help="Max concurrent chapters (default: 1 = sequential)",
    )
    p_all.add_argument(
        "--model", "-m", default=None,
        help="Model alias (haiku/sonnet/opus) or full model name (default: sonnet)",
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
