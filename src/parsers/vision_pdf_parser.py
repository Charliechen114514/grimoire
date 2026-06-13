"""扫描版 PDF 视觉解析器 — 把纯扫描书（无文字层）逐页渲染成图，调视觉 LLM
转写为 Markdown（正文 + LaTeX 公式 + 表格），并按模型返回的 bbox 裁切插图嵌入。

复用：
- pdf_parser._extract_chapter_toc()  定位章节边界（扫描书的 get_toc() 完好）
- vision_client.vision_transcribe()  智谱 OpenAI 兼容视觉调用

产出 ChaptersRaw：每章一段 Markdown 文本，图引用 images/{filename}。
"""
from __future__ import annotations

import asyncio
import json
import re
from datetime import datetime, timezone

import pymupdf

from src.agents.vision_client import vision_transcribe
from src.config import VISION_MODEL, book_data_dir
from src.log import logger
from src.schema import ChaptersRaw, SourceMeta, TocEntry

from .base import BaseParser
from .pdf_parser import _extract_chapter_toc

# 渲染给视觉模型的页面宽度（px）。电子学 PDF 页面坐标系异常大（1490pt），
# 用矩阵缩放到此宽度，既省 token 又避免 Marker 那种 4k 巨图爆内存。
_TARGET_WIDTH = 1500
# 裁切插图时相对发送分辨率的放大倍数（让插图更清晰）
_CROP_SCALE_FACTOR = 1.5
_MIN_BBOX_AREA = 0.0005  # 归一化面积下限，过滤过小的 bbox

_PROMPT_TMPL = """你是教材扫描页 OCR 转写专家。请把这页精确转写为 Markdown：
1. 正文逐字照录，保留段落与阅读顺序。
2. 数学公式用 LaTeX：行内 $...$，独立公式 $$...$$。
3. 表格用 Markdown 表格语法。
4. 标题用 # / ## 表示层级。
5. 电路图/原理图/波形图/照片等插图：不要描述或重画其内部细节，在图中出现的位置插入引用并紧跟图注：
   ![figure](images/{FILENAME})
   **（图注文字）**
   FILENAME 命名：{prefix}_fig{n}.png，n 从 1 按从上到下顺序。
6. 忽略页眉、页脚、页码、水印（如 ebrary 引用行）。
7. 在全部 Markdown 之后另起一行（仅此一行）输出本页插图的裁切坐标，格式严格为：
   FIGURES_JSON: [{"filename":"{prefix}_fig1.png","bbox":[x1,y1,x2,y2],"caption":"..."}]
   bbox 是插图矩形在整页中的位置，坐标归一化到 [0,1]，原点左上角，[x1,y1]=左上 [x2,y2]=右下。
   若本页无插图，输出：FIGURES_JSON: []

本页 FILENAME 前缀：{prefix}"""

_FIG_MARKER = "FIGURES_JSON:"
_REF_RE = re.compile(r"!\[[^\]]*\]\(images/([^)]+)\)")
_FENCE_RE = re.compile(r"```(?:json)?\s*\n?(.*?)```", re.DOTALL)


class VisionPDFParser(BaseParser):
    """扫描版 PDF 视觉解析器。

    Args:
        model: 智谱视觉模型名（默认 config.VISION_MODEL = glm-4.5v）
        target_width: 渲染发送给模型的页面宽度 px
        concurrency: 并发转写页数
        max_pages: 测试用——最多处理这么多页（跨章节累计）
    """

    def __init__(
        self,
        *,
        model: str | None = None,
        target_width: int = _TARGET_WIDTH,
        concurrency: int = 4,
        max_pages: int | None = None,
    ) -> None:
        self.model = model or VISION_MODEL
        self.target_width = target_width
        self.concurrency = concurrency
        self.max_pages = max_pages

    # ── BaseParser 接口 ──
    def parse(self, source: str, book_slug: str) -> ChaptersRaw:
        pdf_path = _resolve_pdf(source)
        logger.info("视觉解析 PDF: {} [slug={} model={}]", pdf_path, book_slug, self.model)

        images_dir = book_data_dir(book_slug) / "images"
        doc = pymupdf.open(str(pdf_path))
        try:
            toc = doc.get_toc()
            chapter_entries = _extract_chapter_toc(toc)

            if not chapter_entries:
                logger.warning("TOC 无章级条目，整本视作单章: {}", pdf_path.name)
                chapter_entries = [(1, pdf_path.stem, 1)]

            # 计算每章页范围（物理页 1-indexed）
            ranges: list[tuple[int, str, int, int]] = []  # (ch_num, title, start, end)
            for i, (ch_num, title, start) in enumerate(chapter_entries):
                end = chapter_entries[i + 1][2] if i + 1 < len(chapter_entries) else doc.page_count + 1
                ranges.append((ch_num, title, start, end))

            chapters: dict[int, str] = {}
            pages_done = 0
            for ch_num, title, start, end in ranges:
                if self.max_pages is not None and pages_done >= self.max_pages:
                    break
                page_indices = list(range(start - 1, min(end - 1, doc.page_count)))
                if self.max_pages is not None:
                    page_indices = page_indices[: self.max_pages - pages_done]
                if not page_indices:
                    continue
                logger.info("第{}章 '{}': {} 页", ch_num, title, len(page_indices))
                md = asyncio.run(
                    self._convert_pages(doc, page_indices, images_dir, ch_num, book_slug)
                )
                chapters[ch_num] = md
                pages_done += len(page_indices)

            toc_entries = [TocEntry(level=lvl, title=t) for lvl, t, _ in toc] if toc else None
            logger.info(
                "视觉解析完成 {}: {} 章, {} 页, 图存于 {}",
                pdf_path.name, len(chapters), pages_done, images_dir,
            )
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
        finally:
            doc.close()

    # ── 逐页并发转写 ──
    async def _convert_pages(
        self,
        doc: pymupdf.Document,
        page_indices: list[int],
        images_dir,
        ch_num: int,
        book_slug: str,
    ) -> str:
        sem = asyncio.Semaphore(self.concurrency)

        async def one(idx: int) -> tuple[int, str]:
            async with sem:
                md = await self._convert_page(doc, idx, images_dir, ch_num, book_slug)
                return idx, md

        results = await asyncio.gather(*(one(i) for i in page_indices))
        results.sort(key=lambda x: x[0])
        return "\n\n---\n\n".join(md for _, md in results)

    async def _convert_page(self, doc, page_idx, images_dir, ch_num, book_slug) -> str:
        page = doc[page_idx]
        zoom = self.target_width / page.rect.width
        pix = page.get_pixmap(matrix=pymupdf.Matrix(zoom, zoom), alpha=False)
        img_bytes = pix.tobytes("png")
        page_num = page_idx + 1
        prefix = f"{book_slug}_ch{ch_num:02d}_p{page_num:05d}"

        prompt = _PROMPT_TMPL.replace("{prefix}", prefix)
        raw = await vision_transcribe(img_bytes, prompt, model=self.model)
        md, figures = _parse_response(raw)

        # 裁切插图
        saved: set[str] = set()
        for fig in figures:
            fn = fig.get("filename", "").strip()
            bbox = fig.get("bbox")
            if not fn or not isinstance(bbox, list) or len(bbox) != 4:
                continue
            try:
                _crop_figure(page, bbox, fn, images_dir, self.target_width)
                saved.add(fn)
            except Exception as e:
                logger.warning("裁图失败 {} (p{}): {}", fn, page_num, e)

        # 处理无法落地的图引用
        md = _finalize_refs(md, saved)
        logger.info("第{}章 p{}: {} 字符, {} 图", ch_num, page_num, len(md), len(saved))
        return md


# ── 辅助函数 ──

def _resolve_pdf(source: str):
    from pathlib import Path

    p = Path(source)
    if not p.exists():
        raise FileNotFoundError(f"PDF not found: {p}")
    return p


def _parse_response(raw: str) -> tuple[str, list[dict]]:
    """从模型输出拆出 Markdown 正文和 FIGURES_JSON 列表。"""
    text = raw.strip()
    marker = text.rfind(_FIG_MARKER)
    figures: list[dict] = []
    md = text
    if marker != -1:
        md = text[:marker].rstrip()
        tail = text[marker + len(_FIG_MARKER):].strip()
        figures = _safe_parse_figures(tail)
    return md, figures


def _safe_parse_figures(tail: str) -> list[dict]:
    """尽力解析 FIGURES_JSON 后的 JSON 数组，容忍 ```json 包裹与尾部噪音。"""
    fence = _FENCE_RE.search(tail)
    candidate = fence.group(1).strip() if fence else tail.strip()
    # 截到第一个完整的 JSON 数组
    start = candidate.find("[")
    end = candidate.rfind("]")
    if start == -1 or end == -1 or end <= start:
        return []
    snippet = candidate[start : end + 1]
    try:
        data = json.loads(snippet)
        if isinstance(data, list):
            return data
    except json.JSONDecodeError:
        pass
    return []


def _crop_figure(page, bbox, filename, images_dir, target_width):
    """按归一化 bbox 从 PDF 页裁切插图并保存。"""
    x1, y1, x2, y2 = (max(0.0, min(1.0, float(v))) for v in bbox)
    if (x2 - x1) * (y2 - y1) < _MIN_BBOX_AREA:
        raise ValueError(f"bbox 面积过小 [{x1},{y1},{x2},{y2}]")
    if x2 <= x1 or y2 <= y1:
        raise ValueError("bbox 非法（宽高<=0）")
    pw, ph = page.rect.width, page.rect.height
    clip = pymupdf.Rect(x1 * pw, y1 * ph, x2 * pw, y2 * ph)
    scale = (target_width / pw) * _CROP_SCALE_FACTOR
    cpix = page.get_pixmap(matrix=pymupdf.Matrix(scale, scale), clip=clip, alpha=False)
    images_dir.mkdir(parents=True, exist_ok=True)
    (images_dir / filename).write_bytes(cpix.tobytes("png"))


def _finalize_refs(md: str, saved: set[str]) -> str:
    """把未能裁出的 image 引用替换为占位，避免死链。"""
    def repl(m: re.Match) -> str:
        fn = m.group(1)
        return m.group(0) if fn in saved else "*[图：见原文]*"
    return _REF_RE.sub(repl, md)
