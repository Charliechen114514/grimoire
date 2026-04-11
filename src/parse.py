"""CLI wrapper for PDF parsing (Phase 1)."""
import argparse
import sys
from pathlib import Path

from src.log import logger
from src.pdf_parser import save_chapters_raw, split_book


def main() -> None:
    parser = argparse.ArgumentParser(
        description="Parse a PDF textbook into per-chapter text (Phase 1)"
    )
    parser.add_argument("pdf", type=Path, help="Path to the PDF file")
    parser.add_argument("--slug", "-s", required=True, help="Book slug (e.g. MYBOOK)")
    parser.add_argument(
        "--verbose", "-v", action="store_true", help="Enable debug logging"
    )
    args = parser.parse_args()

    from src.log import setup_logging
    setup_logging(verbose=args.verbose)

    pdf_path: Path = args.pdf
    if not pdf_path.exists():
        print(f"Error: file not found: {pdf_path}", file=sys.stderr)
        sys.exit(1)

    chapters = split_book(pdf_path, book_slug=args.slug)
    if not chapters:
        print("Error: no chapters found in PDF TOC", file=sys.stderr)
        sys.exit(1)

    out = save_chapters_raw(chapters, book_slug=args.slug, pdf_path=pdf_path)
    print(f"OK: {len(chapters)} chapters -> {out}")


if __name__ == "__main__":
    main()
