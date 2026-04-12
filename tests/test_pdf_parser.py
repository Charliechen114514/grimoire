"""PDF 解析模块测试 — 迁移到当前 parsers API。"""
import json
import os
from datetime import datetime, timezone
from pathlib import Path

import pymupdf
import pytest

from src.parsers.pdf_parser import (
    _extract_chapter_toc,
    _extract_chapters_from_pdf,
    PDFParser,
)
from src.parsers import save_chapters_raw, load_chapters_raw
from src.schema import ChaptersRaw, SourceMeta
from src.config import BOOKS_DIR

# ── TOC 样本（模拟 CSAPP 的 TOC 结构） ──
SAMPLE_TOC = [
    (1, "Front Cover", 1),
    (1, "Contents", 9),
    (1, "Chapter 1: A Tour of Computer Systems", 39),
    (2, "1.1: Information Is Bits + Context", 41),
    (2, "1.2: Programs Are Translated by Other Programs", 42),
    (1, "Part I: Program Structure and Execution", 67),
    (2, "Chapter 2: Representing and Manipulating Information", 69),
    (3, "2.1: Information Storage", 72),
    (2, "Chapter 3: Machine-Level Representation", 201),
]

# 跳过无 PDF 的环境
CSAPP_PDF = list(BOOKS_DIR.glob("*.pdf"))[0] if BOOKS_DIR.exists() else None
skip_no_pdf = pytest.mark.skipif(CSAPP_PDF is None, reason="No PDF in books/")


# ── 单元测试：TOC 解析 ──


class TestExtractChapterToc:
    def test_extracts_chapters(self):
        chapters = _extract_chapter_toc(SAMPLE_TOC)
        assert len(chapters) == 3
        nums = [c[0] for c in chapters]
        assert nums == [1, 2, 3]

    def test_chapter_pages(self):
        chapters = _extract_chapter_toc(SAMPLE_TOC)
        assert chapters[0] == (1, "Chapter 1: A Tour of Computer Systems", 39)
        assert chapters[1] == (2, "Chapter 2: Representing and Manipulating Information", 69)
        assert chapters[2] == (3, "Chapter 3: Machine-Level Representation", 201)

    def test_empty_toc(self):
        assert _extract_chapter_toc([]) == []

    def test_no_chapter_pattern_falls_back_to_l1(self):
        """无 'Chapter N' 时回退到 L1 条目顺序编号（跳过非正文）。"""
        toc = [(1, "Introduction", 1), (2, "Section 1.1", 3)]
        result = _extract_chapter_toc(toc)
        # "Introduction" 是 L1 条目，不被 _SKIP_L1 过滤，所以回退为第 1 章
        assert len(result) == 1
        assert result[0] == (1, "Introduction", 1)

    def test_case_insensitive(self):
        toc = [(1, "CHAPTER 5: Testing", 100)]
        chapters = _extract_chapter_toc(toc)
        assert len(chapters) == 1
        assert chapters[0][0] == 5


# ── 单元测试：save/load chapters_raw ──


def _make_sample_raw(slug: str = "TESTBOOK", n_chapters: int = 2) -> ChaptersRaw:
    return ChaptersRaw(
        chapters={str(i): f"Chapter {i} text" for i in range(1, n_chapters + 1)},
        metadata=SourceMeta(
            source_type="pdf",
            source_uri="test_book.pdf",
            book_slug=slug,
            total_chapters=n_chapters,
            parse_timestamp=datetime.now(timezone.utc).isoformat(),
        ),
    )


class TestSaveChaptersRaw:
    def test_save_and_load(self, tmp_path, monkeypatch):
        monkeypatch.setattr("src.config.DATA_DIR", tmp_path)

        data = _make_sample_raw("TESTBOOK")
        result = save_chapters_raw(data, "TESTBOOK")

        assert result.exists()
        loaded = load_chapters_raw("TESTBOOK")
        assert loaded.metadata.total_chapters == 2
        assert loaded.metadata.book_slug == "TESTBOOK"
        assert loaded.chapters["1"] == "Chapter 1 text"

    def test_no_temp_residue(self, tmp_path, monkeypatch):
        monkeypatch.setattr("src.config.DATA_DIR", tmp_path)

        data = _make_sample_raw("ATOMICTEST", 1)
        save_chapters_raw(data, "ATOMICTEST")

        data_dir = tmp_path / "ATOMICTEST"
        tmp_files = [f for f in os.listdir(data_dir) if f.endswith(".tmp")]
        assert tmp_files == []


# ── 集成测试：真实 PDF ──


@skip_no_pdf
class TestIntegration:
    def test_extract_chapters(self):
        chapters, toc = _extract_chapters_from_pdf(CSAPP_PDF)
        assert len(chapters) >= 1
        # 每章至少有一定文本量
        for idx in sorted(chapters.keys())[:3]:
            assert len(chapters[idx]) > 100, f"Chapter {idx} too short"

    def test_chapter_1_no_garbage(self):
        chapters, toc = _extract_chapters_from_pdf(CSAPP_PDF)
        text = chapters[sorted(chapters.keys())[0]]
        # 不应有明显乱码
        assert "\ufffd" not in text[:2000]
        # 验证是有效文本内容
        assert len(text) > 100

    def test_save_full_pipeline(self, tmp_path, monkeypatch):
        monkeypatch.setattr("src.config.DATA_DIR", tmp_path)

        chapters, toc = _extract_chapters_from_pdf(CSAPP_PDF)
        raw = ChaptersRaw(
            chapters={str(k): v for k, v in chapters.items()},
            metadata=SourceMeta(
                source_type="pdf",
                source_uri=CSAPP_PDF.name,
                book_slug="CSAPP",
                total_chapters=len(chapters),
                parse_timestamp=datetime.now(timezone.utc).isoformat(),
            ),
        )
        result = save_chapters_raw(raw, "CSAPP")

        loaded = load_chapters_raw("CSAPP")
        assert loaded.metadata.total_chapters == len(chapters)
        assert loaded.metadata.book_slug == "CSAPP"


# ── 单元测试：PDFParser 类 ──


class TestPDFParser:
    def test_default_extract_images(self):
        parser = PDFParser()
        assert parser.extract_images is True

    def test_no_images_flag(self):
        parser = PDFParser(extract_images=False)
        assert parser.extract_images is False
