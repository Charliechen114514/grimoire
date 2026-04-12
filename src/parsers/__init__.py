"""Parsers package — 多数据源解析器。

提供统一的解析接口和工具函数：
- get_parser(): 根据数据源类型自动选择解析器
- save_chapters_raw(): 将 ChaptersRaw 持久化到磁盘
- load_chapters_raw(): 从磁盘加载 ChaptersRaw
"""

import json
import os
import tempfile
from pathlib import Path

from src.config import book_data_dir
from src.log import logger
from src.schema import ChaptersRaw

from .base import BaseParser
from .pdf_parser import PDFParser

__all__ = [
    "BaseParser",
    "PDFParser",
    "get_parser",
    "save_chapters_raw",
    "load_chapters_raw",
]


class _WebParserAdapter(BaseParser):
    """适配器：将 Web 引擎包装成 BaseParser 接口。"""

    def __init__(self, engine):
        self._engine = engine

    def parse(self, source: str, book_slug: str) -> ChaptersRaw:
        return self._engine.parse(source, book_slug)


def get_parser(
    source: str,
    source_type: str | None = None,
    engine: str | None = None,
    *,
    extract_images: bool = True,
    **kwargs,
) -> BaseParser:
    """
    根据数据源自动选择解析器。

    Args:
        source: 文件路径或 URL
        source_type: 显式指定类型 ("pdf" | "web")，不指定则自动检测
        engine: Web 引擎名称（如 "wolai"、"static"、"playwright"）或 .py 文件路径
        extract_images: PDF 解析时是否提取图片（默认 True）
        **kwargs: 传递给引擎的额外参数

    Returns:
        对应的 BaseParser 实例
    """
    # PDF 始终走 PDFParser
    if source_type == "pdf" or (not source_type and _is_pdf(source)):
        return PDFParser(extract_images=extract_images)

    # Web 类型
    if source_type == "web" or source.startswith(("http://", "https://")):
        from src.parsers.engines import detect_engine, get_engine

        if engine:
            eng = get_engine(engine, **kwargs)
        else:
            # 自动检测引擎
            engine_cls = detect_engine(source)
            if engine_cls:
                logger.info("Auto-detected engine: {}", engine_cls.NAME)
                eng = engine_cls(**kwargs)
            else:
                # 默认回退到 static
                from src.parsers.engines import get_engine as _ge
                eng = _ge("static", **kwargs)

        return _WebParserAdapter(eng)

    raise ValueError(
        f"Cannot detect source type for '{source}'. "
        f"Use --source-type to specify (pdf/web)."
    )


def _is_pdf(source: str) -> bool:
    return Path(source).suffix.lower() == ".pdf"


def save_chapters_raw(data: ChaptersRaw, book_slug: str) -> Path:
    """
    将 ChaptersRaw 持久化为 data/{slug}/chapters_raw.json（原子写入）。

    Args:
        data: 标准化的章节数据
        book_slug: 项目标识符

    Returns:
        写入的文件路径
    """
    data_dir = book_data_dir(book_slug)
    output_path = data_dir / "chapters_raw.json"

    payload = data.to_json_dict()

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

    logger.info(
        "Saved chapters_raw.json: {} chapters -> {}",
        data.metadata.total_chapters, output_path,
    )
    return output_path


def load_chapters_raw(book_slug: str) -> ChaptersRaw:
    """
    从 data/{slug}/chapters_raw.json 加载标准格式数据。

    Raises:
        FileNotFoundError: 文件不存在
    """
    path = book_data_dir(book_slug) / "chapters_raw.json"
    if not path.exists():
        raise FileNotFoundError(
            f"chapters_raw.json not found at {path}. "
            f"Run 'parse' command first."
        )
    data = json.loads(path.read_text(encoding="utf-8"))
    result = ChaptersRaw.from_json_dict(data)
    logger.info(
        "Loaded {}: {} chapters [{}]",
        path, result.metadata.total_chapters, result.metadata.source_type,
    )
    return result
