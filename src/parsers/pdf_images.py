"""PDF 图片提取 — 从非扫描稿 PDF 中提取内嵌图片并以 Markdown 引用嵌入文本。

采用双通道策略：
1. page.get_text("dict") 提取文本块（保留阅读顺序）
2. page.get_images() + get_image_rects() 提取图片并按 Y 坐标插入文本流

这种方式能处理 get_text("dict") 不返回 type=1 图片块的 PDF
（许多技术书籍的图片不以 inline image block 形式嵌入）。
"""

from pathlib import Path

import pymupdf

from src.log import logger

# 最小图片尺寸（px），低于此值的图片视为装饰性元素跳过
_MIN_IMAGE_SIZE = 20

# 最小显示尺寸（pt），低于此值视为装饰元素跳过
_MIN_DISPLAY_SIZE = 10

# 全页图片面积占比阈值，超过此值视为扫描稿页面跳过
_FULL_PAGE_AREA_RATIO = 0.80


def extract_page_blocks(
    page: pymupdf.Page,
    images_dir: Path,
    chapter_num: int,
    image_counter: dict[str, int],
    saved_images: dict[int, str],
) -> str:
    """从单个 PDF 页面提取交织的文本和图片，返回 Markdown 字符串。

    Args:
        page: pymupdf Page 对象
        images_dir: 图片保存目录
        chapter_num: 章节号（用于文件命名）
        image_counter: 可变计数器 {"count": N}，跨页递增
        saved_images: 已保存图片映射 xref → 相对路径（跨页去重）

    Returns:
        包含文本和内联 Markdown 图片引用的字符串
    """
    doc = page.parent

    # ── 1. 提取文本块 + Y 坐标 ──
    blocks_data = page.get_text("dict", flags=pymupdf.TEXT_PRESERVE_WHITESPACE)
    text_blocks: list[dict] = []
    for block in blocks_data.get("blocks", []):
        if block.get("type") != 0:
            continue
        text = _extract_text_from_block(block)
        if text.strip():
            bbox = block.get("bbox", (0, 0, 0, 0))
            text_blocks.append({
                "y": bbox[1],
                "content": text.strip(),
                "type": "text",
            })

    # ── 2. 提取图片 + Y 坐标 ──
    image_blocks: list[dict] = []
    page_rect = page.rect
    page_area = page_rect.width * page_rect.height

    for img_info in page.get_images(full=True):
        xref = img_info[0]

        # 获取图片在页面上的位置
        try:
            rects = page.get_image_rects(xref)
        except Exception:
            continue
        if not rects:
            continue

        rect = rects[0]
        bw, bh = rect.width, rect.height

        # 跳过太小的图片（装饰元素）
        if bw < _MIN_DISPLAY_SIZE or bh < _MIN_DISPLAY_SIZE:
            continue

        # 跳过全页扫描图片
        img_area = bw * bh
        if page_area > 0 and (img_area / page_area) > _FULL_PAGE_AREA_RATIO:
            logger.debug("Skipping full-page image (xref={})", xref)
            continue

        # 获取图片实际像素尺寸用于过滤
        try:
            img_data = doc.extract_image(xref)
        except Exception:
            continue
        if not img_data or not img_data.get("image"):
            continue

        img_w = img_data.get("width", 0)
        img_h = img_data.get("height", 0)
        if img_w < _MIN_IMAGE_SIZE or img_h < _MIN_IMAGE_SIZE:
            continue

        # 去重：同一 xref 只保存一次
        if xref in saved_images:
            image_blocks.append({
                "y": rect.y0,
                "content": f"![figure]({saved_images[xref]})",
                "type": "image",
            })
            continue

        # 保存图片到磁盘
        ext = img_data.get("ext", "png")
        rel_path = _save_image_block(
            img_data["image"], ext, images_dir, chapter_num, image_counter,
        )
        if rel_path:
            saved_images[xref] = rel_path
            image_blocks.append({
                "y": rect.y0,
                "content": f"![figure]({rel_path})",
                "type": "image",
            })

    # ── 3. 按 Y 坐标合并文本和图片 ──
    if image_blocks:
        logger.info(
            "Page {}: found {} image(s) among {} text block(s)",
            page.number + 1, len(image_blocks), len(text_blocks),
        )

    all_blocks = text_blocks + image_blocks
    all_blocks.sort(key=lambda b: b["y"])

    parts = [b["content"] for b in all_blocks]
    return "\n\n".join(parts) if parts else ""


def _extract_text_from_block(block: dict) -> str:
    """从 get_text("dict") 的文本块中提取纯文本。"""
    lines_text: list[str] = []
    for line in block.get("lines", []):
        spans_text = []
        for span in line.get("spans", []):
            text = span.get("text", "")
            if text:
                spans_text.append(text)
        if spans_text:
            lines_text.append("".join(spans_text))
    return "\n".join(lines_text)


def _save_image_block(
    img_bytes: bytes,
    ext: str,
    images_dir: Path,
    chapter_num: int,
    image_counter: dict[str, int],
) -> str | None:
    """保存图片块到磁盘。

    Returns:
        相对路径（如 "images/ch01_fig001.png"）或 None
    """
    if not img_bytes:
        return None

    image_counter["count"] += 1
    fig_num = image_counter["count"]
    filename = f"ch{chapter_num:02d}_fig{fig_num:03d}.{ext}"

    images_dir.mkdir(parents=True, exist_ok=True)
    filepath = images_dir / filename
    filepath.write_bytes(img_bytes)

    logger.debug("Extracted image: {} ({} bytes)", filename, len(img_bytes))

    return f"images/{filename}"
