"""向后兼容 shim — 重新导出 parsers.pdf_parser 中的公共 API。

旧代码中 `from src.pdf_parser import split_book, save_chapters_raw` 仍然有效。
新代码应使用 `from src.parsers import PDFParser, save_chapters_raw`。
"""

from src.parsers.pdf_parser import (
    PDFParser,
    _extract_chapter_toc,
    _extract_chapters_from_pdf,
    _extract_page_text,
)
from src.parsers import save_chapters_raw

from pathlib import Path
from src.log import logger


def split_book(
    pdf_path: Path,
    book_slug: str,
) -> tuple[dict[int, str], list[tuple[int, str, int]]]:
    """
    将整本 PDF 按章节切割为文本字典。

    保留旧签名以保证向后兼容。
    新代码建议使用 PDFParser.parse() 返回 ChaptersRaw。
    """
    if not pdf_path.exists():
        raise FileNotFoundError(f"PDF not found: {pdf_path}")

    logger.info("Splitting book '{}': {}", book_slug, pdf_path)
    chapters, toc = _extract_chapters_from_pdf(pdf_path)
    logger.info("Book '{}': {} chapters extracted", book_slug, len(chapters))
    return chapters, toc


def parse_chapter(pdf_path: Path, chapter_n: int) -> str:
    """从 PDF 中提取第 N 章的干净文本。"""
    if not pdf_path.exists():
        raise FileNotFoundError(f"PDF not found: {pdf_path}")

    chapters, _toc = _extract_chapters_from_pdf(pdf_path)

    if chapter_n not in chapters:
        available = sorted(chapters.keys())
        raise ValueError(f"Chapter {chapter_n} not found. Available: {available}")

    logger.info("Extracted chapter {}: {} chars", chapter_n, len(chapters[chapter_n]))
    return chapters[chapter_n]


__all__ = [
    "split_book",
    "parse_chapter",
    "save_chapters_raw",
    "PDFParser",
]
