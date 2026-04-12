"""PDF 解析器 — 从 PDF 文件提取章节文本，输出标准 ChaptersRaw 格式。

核心逻辑来自原 src/pdf_parser.py，封装为 BaseParser 子类。
"""

import re
from datetime import datetime, timezone
from pathlib import Path

import pymupdf

from src.log import logger
from src.schema import ChaptersRaw, SourceMeta, TocEntry

from .base import BaseParser

_SKIP_L1 = re.compile(
    r"^(?:cover|title\s*page|copyright|dedication|about|"
    r"contributor|table\s*of\s*contents|contents\s*at\s*a\s*glance|"
    r"preface|foreword|acknowledgment|index|"
    r"other\s*books?\s*you\s*may\s*enjoy|"
    r"appendix)",
    re.IGNORECASE,
)


def _extract_chapter_toc(toc: list[tuple[int, str, int]]) -> list[tuple[int, str, int]]:
    """
    从 TOC 中筛选出章级条目。

    策略：
    1. 优先匹配 "Chapter N" 格式的标题
    2. 若无匹配，回退：将所有 L1 条目按顺序编号为章节，
       跳过 Preface / Index / Cover 等非正文条目
    """
    # ── 策略 1：匹配 "Chapter N" ──
    pattern = re.compile(r"Chapter\s+(\d+)", re.IGNORECASE)
    chapters = []
    for _level, title, page in toc:
        m = pattern.search(title)
        if m:
            chapters.append((int(m.group(1)), title, page))

    if chapters:
        chapters.sort(key=lambda x: x[0])
        return chapters

    # ── 策略 2：回退 — L1 条目顺序编号 ──
    logger.info("No 'Chapter N' entries found, falling back to L1-based detection")
    ch_num = 0
    for level, title, page in toc:
        if level != 1:
            continue
        if _SKIP_L1.search(title.strip()):
            continue
        if page < 1:
            continue
        ch_num += 1
        chapters.append((ch_num, title.strip(), page))

    chapters.sort(key=lambda x: x[0])
    return chapters


def _extract_page_text(
    doc: pymupdf.Document,
    start_page: int,
    end_page: int,
    *,
    images_dir: Path | None = None,
    chapter_num: int = 0,
    image_counter: dict[str, int] | None = None,
    saved_images: dict[int, str] | None = None,
) -> str:
    """从 PDF 中提取指定页范围的文本（可选含图片）。"""
    parts: list[str] = []
    for page_idx in range(start_page - 1, min(end_page - 1, doc.page_count)):
        page = doc[page_idx]
        if images_dir and image_counter is not None and saved_images is not None:
            from .pdf_images import extract_page_blocks

            text = extract_page_blocks(
                page, images_dir, chapter_num, image_counter, saved_images,
            )
        else:
            text = page.get_text()
        if text.strip():
            parts.append(text.strip())

    return "\n\n".join(parts)


def _extract_chapters_from_pdf(
    pdf_path: Path,
    *,
    book_slug: str = "",
    extract_images: bool = True,
) -> tuple[dict[int, str], list[tuple[int, str, int]]]:
    """
    用 pymupdf TOC 定位章节边界，按页范围提取文本（含可选图片提取）。

    Returns:
        (chapters, toc) — {chapter_num: text} 和原始 TOC
    """
    doc = pymupdf.open(str(pdf_path))
    try:
        toc = doc.get_toc()
        chapter_entries = _extract_chapter_toc(toc)

        if not chapter_entries:
            logger.warning("No chapter entries found in TOC for {}", pdf_path)
            return {}, toc

        # 图片提取状态（跨章节共享）
        images_dir: Path | None = None
        image_counter: dict[str, int] | None = None
        saved_images: dict[int, str] | None = None
        if extract_images and book_slug:
            from src.config import book_data_dir

            images_dir = book_data_dir(book_slug) / "images"
            image_counter = {"count": 0}
            saved_images = {}

        chapters: dict[int, str] = {}
        for i, (ch_num, title, start_page) in enumerate(chapter_entries):
            if i + 1 < len(chapter_entries):
                end_page = chapter_entries[i + 1][2]
            else:
                end_page = doc.page_count + 1

            text = _extract_page_text(
                doc,
                start_page,
                end_page,
                images_dir=images_dir,
                chapter_num=ch_num,
                image_counter=image_counter,
                saved_images=saved_images,
            )
            chapters[ch_num] = text
            logger.debug(
                "Chapter {} '{}': pages {}-{}, {} chars",
                ch_num, title, start_page, end_page - 1, len(text),
            )

        img_count = image_counter["count"] if image_counter else 0
        logger.info(
            "Extracted {} chapters from {}: {} ({} images)",
            len(chapters), pdf_path.name, sorted(chapters.keys()), img_count,
        )
        return chapters, toc
    finally:
        doc.close()


class PDFParser(BaseParser):
    """PDF 文件解析器，使用 pymupdf 提取章节文本。"""

    def __init__(self, extract_images: bool = True) -> None:
        self.extract_images = extract_images

    def parse(self, source: str, book_slug: str) -> ChaptersRaw:
        """
        从 PDF 文件中提取所有章节。

        Args:
            source: PDF 文件路径
            book_slug: 项目标识符
        """
        pdf_path = Path(source)
        if not pdf_path.exists():
            raise FileNotFoundError(f"PDF not found: {pdf_path}")

        logger.info("Parsing PDF: {} [slug={}]", pdf_path, book_slug)
        chapters, toc = _extract_chapters_from_pdf(
            pdf_path,
            book_slug=book_slug,
            extract_images=self.extract_images,
        )

        if not chapters:
            raise ValueError(f"No chapters found in PDF TOC: {pdf_path}")

        toc_entries = None
        if toc:
            toc_entries = [TocEntry(level=lvl, title=title) for lvl, title, _page in toc]

        return ChaptersRaw(
            chapters={str(k): v for k, v in chapters.items()},
            metadata=SourceMeta(
                source_type="pdf",
                source_uri=pdf_path.name,
                book_slug=book_slug,
                total_chapters=len(chapters),
                parse_timestamp=datetime.now(timezone.utc).isoformat(),
                toc=toc_entries,
            ),
        )
