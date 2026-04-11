"""PDF 解析核心模块 — pymupdf 提取文本 + TOC 章节定位"""
import json
import logging
import os
import re
import tempfile
from datetime import datetime, timezone
from pathlib import Path

import pymupdf

from src.config import book_data_dir

logger = logging.getLogger(__name__)


def _extract_chapter_toc(toc: list[tuple[int, str, int]]) -> list[tuple[int, str, int]]:
    """
    从 TOC 中筛选出章级条目（含 'Chapter' 关键字）。

    Args:
        toc: pymupdf 的 get_toc() 返回值 [(level, title, page), ...]

    Returns:
        [(chapter_num, title, start_page), ...] 按章节号排序
    """
    pattern = re.compile(r"Chapter\s+(\d+)", re.IGNORECASE)
    chapters = []
    for _level, title, page in toc:
        m = pattern.search(title)
        if m:
            chapters.append((int(m.group(1)), title, page))

    chapters.sort(key=lambda x: x[0])
    return chapters


def _extract_page_text(doc: pymupdf.Document, start_page: int, end_page: int) -> str:
    """
    从 PDF 中提取指定页范围的纯文本。

    Args:
        doc: 已打开的 pymupdf Document
        start_page: 起始页码（1-indexed，TOC 的页码体系）
        end_page: 结束页码（1-indexed，不含此页）
    """
    # pymupdf 页索引是 0-based
    parts: list[str] = []
    for page_idx in range(start_page - 1, min(end_page - 1, doc.page_count)):
        page = doc[page_idx]
        text = page.get_text()
        if text.strip():
            parts.append(text.strip())

    return "\n\n".join(parts)


def _extract_chapters_from_pdf(pdf_path: Path) -> dict[int, str]:
    """
    用 pymupdf TOC 定位章节边界，按页范围提取文本。

    Args:
        pdf_path: PDF 文件路径

    Returns:
        {chapter_num: chapter_text} 字典
    """
    doc = pymupdf.open(str(pdf_path))
    try:
        toc = doc.get_toc()
        chapter_entries = _extract_chapter_toc(toc)

        if not chapter_entries:
            logger.warning("No chapter entries found in TOC for %s", pdf_path)
            return {}

        chapters: dict[int, str] = {}
        for i, (ch_num, title, start_page) in enumerate(chapter_entries):
            # 下一章的起始页作为本章的结束页
            if i + 1 < len(chapter_entries):
                end_page = chapter_entries[i + 1][2]
            else:
                end_page = doc.page_count + 1

            text = _extract_page_text(doc, start_page, end_page)
            chapters[ch_num] = text
            logger.debug(
                "Chapter %d '%s': pages %d-%d, %d chars",
                ch_num, title, start_page, end_page - 1, len(text),
            )

        logger.info(
            "Extracted %d chapters from %s: %s",
            len(chapters), pdf_path.name, sorted(chapters.keys()),
        )
        return chapters
    finally:
        doc.close()


def parse_chapter(pdf_path: Path, chapter_n: int) -> str:
    """
    从 PDF 中提取第 N 章的干净文本。

    Args:
        pdf_path: PDF 文件路径
        chapter_n: 章节编号（1-indexed）

    Returns:
        该章节的文本

    Raises:
        ValueError: chapter_n 不存在
        FileNotFoundError: pdf_path 不存在
    """
    if not pdf_path.exists():
        raise FileNotFoundError(f"PDF not found: {pdf_path}")

    chapters = _extract_chapters_from_pdf(pdf_path)

    if chapter_n not in chapters:
        available = sorted(chapters.keys())
        raise ValueError(f"Chapter {chapter_n} not found. Available: {available}")

    logger.info("Extracted chapter %d: %d chars", chapter_n, len(chapters[chapter_n]))
    return chapters[chapter_n]


def split_book(pdf_path: Path, book_slug: str) -> dict[int, str]:
    """
    将整本 PDF 按章节切割为文本字典。

    Args:
        pdf_path: PDF 文件路径
        book_slug: 书籍短名，用于日志标识

    Returns:
        {chapter_idx: chapter_text} 字典，chapter_idx 从 1 开始
    """
    if not pdf_path.exists():
        raise FileNotFoundError(f"PDF not found: {pdf_path}")

    logger.info("Splitting book '%s': %s", book_slug, pdf_path)
    chapters = _extract_chapters_from_pdf(pdf_path)
    logger.info("Book '%s': %d chapters extracted", book_slug, len(chapters))
    return chapters


def save_chapters_raw(
    chapters: dict[int, str],
    book_slug: str,
    pdf_path: Path,
) -> Path:
    """
    将章节字典持久化为 data/{slug}/chapters_raw.json（原子写入）。

    Args:
        chapters: {chapter_idx: chapter_text} 字典
        book_slug: 书籍短名
        pdf_path: 原始 PDF 路径（记入 metadata）

    Returns:
        写入的文件路径
    """
    data_dir = book_data_dir(book_slug)
    output_path = data_dir / "chapters_raw.json"

    payload: dict = {}
    for idx in sorted(chapters.keys()):
        payload[str(idx)] = chapters[idx]
    payload["metadata"] = {
        "source_pdf": pdf_path.name,
        "book_slug": book_slug,
        "total_chapters": len(chapters),
        "parse_timestamp": datetime.now(timezone.utc).isoformat(),
    }

    data_dir.mkdir(parents=True, exist_ok=True)
    fd, tmp_path = tempfile.mkstemp(suffix=".json", dir=str(data_dir))
    try:
        with os.fdopen(fd, "w", encoding="utf-8") as f:
            json.dump(payload, f, ensure_ascii=False, indent=2)
        os.replace(tmp_path, output_path)
    except BaseException:
        if os.path.exists(tmp_path):
            os.unlink(tmp_path)
        raise

    logger.info("Saved chapters_raw.json: %d chapters -> %s", len(chapters), output_path)
    return output_path
