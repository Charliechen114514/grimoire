"""CLI wrapper for PDF parsing (Phase 1)."""
import argparse
import logging
import sys
from pathlib import Path

from src.pdf_parser import save_chapters_raw, split_book

logger = logging.getLogger(__name__)


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

    logging.basicConfig(
        level=logging.DEBUG if args.verbose else logging.INFO,
        format="%(levelname)s %(name)s: %(message)s",
    )

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
