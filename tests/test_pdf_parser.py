"""PDF 解析模块测试"""
import json
import os
from pathlib import Path

import pymupdf
import pytest

from src.config import BOOKS_DIR
from src.pdf_parser import (
    _extract_chapter_toc,
    _extract_chapters_from_pdf,
    save_chapters_raw,
)

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

    def test_no_chapters(self):
        toc = [(1, "Introduction", 1), (2, "Section 1.1", 3)]
        assert _extract_chapter_toc(toc) == []

    def test_case_insensitive(self):
        toc = [(1, "CHAPTER 5: Testing", 100)]
        chapters = _extract_chapter_toc(toc)
        assert len(chapters) == 1
        assert chapters[0][0] == 5


# ── 单元测试：原子写入 ──


class TestSaveChaptersRaw:
    def test_save_and_load(self, tmp_path, monkeypatch):
        monkeypatch.setattr("src.config.DATA_DIR", tmp_path)

        chapters = {1: "Chapter 1 text", 2: "Chapter 2 text"}
        result = save_chapters_raw(chapters, "TESTBOOK", Path("test_book.pdf"))

        assert result.exists()
        data = json.loads(result.read_text(encoding="utf-8"))
        assert data["1"] == "Chapter 1 text"
        assert data["2"] == "Chapter 2 text"
        assert data["metadata"]["total_chapters"] == 2
        assert data["metadata"]["book_slug"] == "TESTBOOK"

    def test_no_temp_residue(self, tmp_path, monkeypatch):
        monkeypatch.setattr("src.config.DATA_DIR", tmp_path)

        save_chapters_raw({1: "Hello"}, "ATOMICTEST", Path("x.pdf"))

        data_dir = tmp_path / "ATOMICTEST"
        tmp_files = [f for f in os.listdir(data_dir) if f.endswith(".tmp")]
        assert tmp_files == []


# ── 集成测试：真实 PDF ──


@skip_no_pdf
class TestIntegration:
    def test_extract_chapters(self):
        chapters = _extract_chapters_from_pdf(CSAPP_PDF)
        assert len(chapters) >= 12
        # 每章至少有一定文本量
        for idx in sorted(chapters.keys())[:3]:
            assert len(chapters[idx]) > 500, f"Chapter {idx} too short"

    def test_chapter_1_no_garbage(self):
        chapters = _extract_chapters_from_pdf(CSAPP_PDF)
        text = chapters[1]
        # 不应有明显乱码
        assert "�" not in text[:2000]
        # 应包含 CSAPP Ch1 的标志性内容
        assert "computer" in text.lower() or "system" in text.lower()

    def test_save_full_pipeline(self, tmp_path, monkeypatch):
        monkeypatch.setattr("src.config.DATA_DIR", tmp_path)

        chapters = _extract_chapters_from_pdf(CSAPP_PDF)
        result = save_chapters_raw(chapters, "CSAPP", CSAPP_PDF)

        data = json.loads(result.read_text(encoding="utf-8"))
        assert data["metadata"]["total_chapters"] == len(chapters)
        assert data["metadata"]["book_slug"] == "CSAPP"
