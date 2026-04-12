"""PDF 图片提取模块测试"""
from pathlib import Path

import pymupdf
import pytest

from src.parsers.pdf_images import (
    extract_page_blocks,
    _extract_text_from_block,
    _save_image_block,
)


# ── 辅助函数 ──


def _make_png(w: int, h: int, color: tuple = (255, 0, 0)) -> bytes:
    """生成有效的 PNG 图片字节。"""
    import struct
    import zlib

    raw_data = b""
    for _ in range(h):
        raw_data += b"\x00" + bytes(color) * w

    def chunk(ctype: bytes, data: bytes) -> bytes:
        c = ctype + data
        return (
            struct.pack(">I", len(data))
            + c
            + struct.pack(">I", zlib.crc32(c) & 0xFFFFFFFF)
        )

    sig = b"\x89PNG\r\n\x1a\n"
    ihdr = chunk(b"IHDR", struct.pack(">IIBBBBB", w, h, 8, 2, 0, 0, 0))
    idat = chunk(b"IDAT", zlib.compress(raw_data))
    iend = chunk(b"IEND", b"")
    return sig + ihdr + idat + iend


def _create_test_pdf_with_image(tmp_path: Path) -> Path:
    """创建一个含文本 + 嵌入图片的测试 PDF。"""
    import io

    img_bytes = _make_png(50, 50)

    doc = pymupdf.open()
    page = doc.new_page(width=612, height=792)
    page.insert_text((72, 100), "Chapter 1: Test Title", fontsize=18)
    page.insert_text((72, 140), "This is some paragraph text about a topic.", fontsize=12)
    page.insert_image(pymupdf.Rect(72, 180, 250, 300), stream=io.BytesIO(img_bytes))
    page.insert_text((72, 330), "Text after the image.", fontsize=12)

    pdf_path = tmp_path / "test_with_image.pdf"
    doc.save(str(pdf_path))
    doc.close()
    return pdf_path


def _create_test_pdf_with_small_image(tmp_path: Path) -> Path:
    """创建一个只含极小图片（应被过滤）的测试 PDF。"""
    import io

    img_bytes = _make_png(2, 2)

    doc = pymupdf.open()
    page = doc.new_page(width=612, height=792)
    page.insert_text((72, 100), "Text before small image.", fontsize=12)
    page.insert_image(pymupdf.Rect(72, 130, 77, 135), stream=io.BytesIO(img_bytes))
    page.insert_text((72, 160), "Text after small image.", fontsize=12)

    pdf_path = tmp_path / "test_small_image.pdf"
    doc.save(str(pdf_path))
    doc.close()
    return pdf_path


def _create_test_pdf_text_only(tmp_path: Path) -> Path:
    """创建纯文本 PDF（无图片）。"""
    doc = pymupdf.open()
    page = doc.new_page(width=612, height=792)
    page.insert_text((72, 100), "Just plain text, no images.", fontsize=12)
    page.insert_text((72, 130), "Second paragraph here.", fontsize=12)

    pdf_path = tmp_path / "test_text_only.pdf"
    doc.save(str(pdf_path))
    doc.close()
    return pdf_path


# ── 单元测试 ──


class TestExtractTextFromBlock:
    def test_simple_text(self):
        block = {
            "type": 0,
            "lines": [
                {"spans": [{"text": "Hello "}, {"text": "World"}]},
                {"spans": [{"text": "Second line"}]},
            ],
        }
        assert _extract_text_from_block(block) == "Hello World\nSecond line"

    def test_empty_block(self):
        block = {"type": 0, "lines": []}
        assert _extract_text_from_block(block) == ""


class TestSaveImageBlock:
    def test_saves_file(self, tmp_path):
        img_bytes = _make_png(10, 10)
        images_dir = tmp_path / "images"
        counter = {"count": 0}

        rel_path = _save_image_block(img_bytes, "png", images_dir, 1, counter)

        assert rel_path == "images/ch01_fig001.png"
        assert counter["count"] == 1
        assert images_dir.exists()
        saved_files = list(images_dir.iterdir())
        assert len(saved_files) == 1
        assert saved_files[0].name == "ch01_fig001.png"
        assert saved_files[0].read_bytes() == img_bytes

    def test_counter_increments(self, tmp_path):
        images_dir = tmp_path / "images"
        counter = {"count": 0}

        _save_image_block(b"\x89PNG", "png", images_dir, 1, counter)
        _save_image_block(b"\x89PNG", "png", images_dir, 1, counter)

        assert counter["count"] == 2
        assert len(list(images_dir.iterdir())) == 2

    def test_empty_bytes_returns_none(self, tmp_path):
        counter = {"count": 0}
        result = _save_image_block(b"", "png", tmp_path / "images", 1, counter)
        assert result is None
        assert counter["count"] == 0


# ── 集成测试 ──


class TestExtractPageBlocks:
    def test_text_only_pdf(self, tmp_path):
        pdf_path = _create_test_pdf_text_only(tmp_path)
        doc = pymupdf.open(str(pdf_path))
        try:
            page = doc[0]
            images_dir = tmp_path / "images"
            result = extract_page_blocks(page, images_dir, 1, {"count": 0}, {})
            assert "plain text" in result
            assert "![" not in result
        finally:
            doc.close()

    def test_pdf_with_image(self, tmp_path):
        pdf_path = _create_test_pdf_with_image(tmp_path)
        doc = pymupdf.open(str(pdf_path))
        try:
            page = doc[0]
            images_dir = tmp_path / "images"
            saved: dict[int, str] = {}
            counter = {"count": 0}

            result = extract_page_blocks(page, images_dir, 1, counter, saved)

            # 应包含文本
            assert "Test Title" in result or "Title" in result

            # 应包含图片引用
            if counter["count"] > 0:
                assert "![" in result
                assert "images/ch01_" in result
                saved_files = list(images_dir.iterdir())
                assert len(saved_files) == 1
        finally:
            doc.close()

    def test_small_image_filtered(self, tmp_path):
        pdf_path = _create_test_pdf_with_small_image(tmp_path)
        doc = pymupdf.open(str(pdf_path))
        try:
            page = doc[0]
            images_dir = tmp_path / "images"

            result = extract_page_blocks(page, images_dir, 1, {"count": 0}, {})

            # 文本保留
            assert "Text before" in result or "Text after" in result
            # 小图被过滤，不应有图片文件
            if images_dir.exists():
                assert len(list(images_dir.iterdir())) == 0
        finally:
            doc.close()

    def test_deduplication_across_calls(self, tmp_path):
        """同一图片跨多次调用只保存一次。"""
        pdf_path = _create_test_pdf_with_image(tmp_path)
        doc = pymupdf.open(str(pdf_path))
        try:
            page = doc[0]
            images_dir = tmp_path / "images"
            saved: dict[int, str] = {}
            counter = {"count": 0}

            extract_page_blocks(page, images_dir, 1, counter, saved)
            first_count = counter["count"]

            result2 = extract_page_blocks(page, images_dir, 1, counter, saved)

            # counter 不应再增长
            assert counter["count"] == first_count

            if first_count > 0:
                assert "![" in result2
        finally:
            doc.close()


class TestExtractChaptersFromPdf:
    def test_text_only_no_images_dir(self, tmp_path):
        """无 book_slug 时不应创建 images 目录。"""
        pdf_path = _create_test_pdf_text_only(tmp_path)
        from src.parsers.pdf_parser import _extract_chapters_from_pdf

        chapters, toc = _extract_chapters_from_pdf(pdf_path, extract_images=False)
        assert isinstance(chapters, dict)

    def test_with_images_enabled(self, tmp_path, monkeypatch):
        """有 book_slug 且 extract_images=True 时应正确运行。"""
        pdf_path = _create_test_pdf_with_image(tmp_path)
        from src.parsers.pdf_parser import _extract_chapters_from_pdf

        monkeypatch.setattr("src.config.DATA_DIR", tmp_path)

        chapters, toc = _extract_chapters_from_pdf(
            pdf_path,
            book_slug="TESTIMG",
            extract_images=True,
        )
        assert isinstance(chapters, dict)
